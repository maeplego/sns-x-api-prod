import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_feed_shows_followed_user_posts(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "display_name": "Alice",
            "birthdate": "1990-01-01", "accept_terms": True,
            "accept_privacy": True,
        },
    )
    bob_signup = await client.post(
        "/auth/signup",
        json={
            "handle": "bob",
            "email": "bob@example.com",
            "password": "password123",
            "display_name": "Bob",
            "birthdate": "1990-01-01", "accept_terms": True,
            "accept_privacy": True,
        },
    )
    bob_me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {bob_signup.json()['access_token']}"},
    )
    bob_id = bob_me.json()["id"]

    alice_login = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

    bob_login = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}

    await client.post(f"/follows/{bob_id}", headers=alice_headers)
    create_post = await client.post(
        "/posts",
        headers=bob_headers,
        json={"body": "bob post for feed"},
    )
    assert create_post.status_code == 202

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.status_code == 200
    body = feed.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["body"] == "bob post for feed"
    assert body["items"][0]["author_handle"] == "bob"
    assert body["next_cursor"] is None
