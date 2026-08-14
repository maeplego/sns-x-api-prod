import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, handle: str, email: str) -> dict:
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


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_blocked_user_posts_hidden_from_feed(client: AsyncClient):
    bob = await _signup(client, "bob", "bob@example.com")
    await _signup(client, "alice", "alice@example.com")

    alice_token = await _login(client, "alice@example.com")
    bob_token = await _login(client, "bob@example.com")
    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "visible before block"})

    feed_before = await client.get("/feed", headers=alice_headers)
    assert len(feed_before.json()["items"]) == 1

    block = await client.post(f"/blocks/{bob['id']}", headers=alice_headers)
    assert block.status_code == 201

    feed_after = await client.get("/feed", headers=alice_headers)
    assert len(feed_after.json()["items"]) == 0


@pytest.mark.asyncio
async def test_followers_only_post_hidden_without_follow(client: AsyncClient):
    bob = await _signup(client, "bob2", "bob2@example.com")
    await _signup(client, "carol", "carol@example.com")
    await _signup(client, "dave", "dave@example.com")

    bob_token = await _login(client, "bob2@example.com")
    carol_token = await _login(client, "carol@example.com")
    dave_token = await _login(client, "dave@example.com")
    bob_headers = {"Authorization": f"Bearer {bob_token}"}
    carol_headers = {"Authorization": f"Bearer {carol_token}"}
    dave_headers = {"Authorization": f"Bearer {dave_token}"}

    # Fan-out writes at publish time — follow before the post.
    await client.post(f"/follows/{bob['id']}", headers=carol_headers)
    await client.post(f"/follows/{bob['id']}", headers=dave_headers)
    await client.post(
        "/posts",
        headers=bob_headers,
        json={"body": "followers only", "visibility": "followers_only"},
    )

    carol_feed = await client.get("/feed", headers=carol_headers)
    assert len(carol_feed.json()["items"]) == 1

    dave_feed = await client.get("/feed", headers=dave_headers)
    assert len(dave_feed.json()["items"]) == 1

    await client.delete(f"/follows/{bob['id']}", headers=dave_headers)
    dave_feed_after = await client.get("/feed", headers=dave_headers)
    assert len(dave_feed_after.json()["items"]) == 0
