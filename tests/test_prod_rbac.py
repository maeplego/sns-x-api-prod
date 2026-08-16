import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.models import User


async def _signup(client: AsyncClient, handle: str, email: str):
    response = await client.post(
        "/auth/signup",
        json={
            "handle": handle,
            "email": email,
            "password": "password123",
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
async def test_user_cannot_suspend(client: AsyncClient):
    user_tokens = await _signup(client, "user1", "user1@example.com")
    target = await _signup(client, "target1", "target1@example.com")
    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    target_id = me.json()["id"]

    response = await client.post(
        f"/moderation/users/{target_id}/suspend",
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
        json={"reason": "spam"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_suspend(client: AsyncClient):
    admin_tokens = await _signup(client, "admin1", "admin1@example.com")
    await _set_role("admin1@example.com", "admin")
    target = await _signup(client, "target2", "target2@example.com")
    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    target_id = me.json()["id"]

    response = await client.post(
        f"/moderation/users/{target_id}/suspend",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        json={"reason": "abuse"},
    )
    assert response.status_code == 204

    blocked = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_report_create(client: AsyncClient):
    tokens = await _signup(client, "reporter", "reporter@example.com")
    target = await _signup(client, "reported", "reported@example.com")
    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    target_id = me.json()["id"]

    response = await client.post(
        "/reports",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "target_type": "user",
            "target_id": target_id,
            "reason": "harassment",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["target_type"] == "user"
