import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.models import User


async def _signup(client: AsyncClient, handle: str, email: str, password: str = "password123"):
    response = await client.post(
        "/auth/signup",
        json={
            "handle": handle,
            "email": email,
            "password": password,
            "display_name": handle.title(),
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _set_role(email: str, role: str) -> None:
    async with database.SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = role
        await session.commit()


@pytest.mark.asyncio
async def test_password_change_invalidates_sessions(client: AsyncClient):
    tokens = await _signup(client, "pwuser", "pwuser@example.com")
    access = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    changed = await client.post(
        "/auth/password",
        headers=headers,
        json={"old_password": "password123", "new_password": "new-password-456"},
    )
    assert changed.status_code == 204

    stale = await client.get("/users/me", headers=headers)
    assert stale.status_code == 401

    login = await client.post(
        "/auth/login",
        json={"email": "pwuser@example.com", "password": "new-password-456"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_account_erasure(client: AsyncClient):
    tokens = await _signup(client, "goneuser", "gone@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    erased = await client.request(
        "DELETE",
        "/users/me",
        headers=headers,
        json={"password": "password123"},
    )
    assert erased.status_code == 204

    login = await client.post(
        "/auth/login",
        json={"email": "gone@example.com", "password": "password123"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_health_ready_and_security_headers(client: AsyncClient):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.headers.get("x-content-type-options") == "nosniff"
    assert health.headers.get("x-frame-options") == "DENY"

    ready = await client.get("/health/ready")
    assert ready.status_code in (200, 503)
    body = ready.json()
    assert body["status"] in ("ready", "not_ready")
    assert "version" in body


@pytest.mark.asyncio
async def test_audit_list_requires_admin(client: AsyncClient):
    user = await _signup(client, "auduser", "auduser@example.com")
    denied = await client.get(
        "/moderation/audit",
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert denied.status_code == 403

    admin = await _signup(client, "audadmin", "audadmin@example.com")
    await _set_role("audadmin@example.com", "admin")
    # re-login not needed; role read from DB on each request
    allowed = await client.get(
        "/moderation/audit",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert allowed.status_code == 200
    assert isinstance(allowed.json(), list)


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_text(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "requests_total" in body
    # Unauthenticated by design for local Prometheus scrape; lock down at the edge if exposed.


@pytest.mark.asyncio
async def test_signup_persists_terms_and_privacy_versions(client: AsyncClient):
    from app.core.legal import PRIVACY_VERSION, TERMS_VERSION

    tokens = await _signup(client, "legalver", "legalver@example.com")
    async with database.SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == "legalver@example.com"))
        assert user is not None
        assert user.terms_version == TERMS_VERSION
        assert user.privacy_version == PRIVACY_VERSION
        assert user.terms_accepted_at is not None
        assert user.privacy_accepted_at is not None
    assert tokens["id"]


def test_production_secrets_reject_example_jwt(monkeypatch):
    from app.core import config
    from app.core.startup import assert_production_secrets

    monkeypatch.setattr(config.settings, "app_env", "production")
    monkeypatch.setattr(
        config.settings,
        "jwt_secret",
        "change-me-in-production-use-a-long-random-string",
    )
    monkeypatch.setattr(config.settings, "postgres_password", "strong-enough-password-here!!")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_production_secrets()


def test_production_docs_url_disabled_when_production():
    """OpenAPI UI is gated at app construction via APP_ENV (see app.main)."""
    from app.main import _is_production, app

    if _is_production:
        assert app.docs_url is None
        assert app.openapi_url is None
    else:
        # Test/CI runs with APP_ENV=test — docs remain available for local exploration.
        assert app.docs_url == "/docs"
