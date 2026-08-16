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
