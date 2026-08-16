import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, handle: str, email: str, password: str = "password123"):
    return await client.post(
        "/auth/signup",
        json={
            "handle": handle,
            "email": email,
            "password": password,
            "display_name": handle.title(),
        },
    )


@pytest.mark.asyncio
async def test_login_returns_refresh_and_refresh_works(client: AsyncClient):
    signup = await _signup(client, "alice", "alice@example.com")
    assert signup.status_code == 201
    body = signup.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    login = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert "access_token" in refresh.json()
    assert "refresh_token" in refresh.json()


@pytest.mark.asyncio
async def test_logout_invalidates_refresh(client: AsyncClient):
    signup = await _signup(client, "bob", "bob@example.com")
    refresh_token = signup.json()["refresh_token"]
    logout = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204
    again = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert again.status_code == 401


@pytest.mark.asyncio
async def test_wrong_password_rejected(client: AsyncClient):
    await _signup(client, "carol", "carol@example.com")
    bad = await client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_bumps_token_version(client: AsyncClient):
    signup = await _signup(client, "dave", "dave@example.com")
    access = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    me = await client.get("/users/me", headers=headers)
    assert me.status_code == 200

    logout_all = await client.post("/auth/logout-all", headers=headers)
    assert logout_all.status_code == 204

    stale = await client.get("/users/me", headers=headers)
    assert stale.status_code == 401
