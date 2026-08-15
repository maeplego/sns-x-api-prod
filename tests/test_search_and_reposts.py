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


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_search_finds_users_and_posts(client: AsyncClient):
    bob = await _signup(client, "bob_search", "bob_search@example.com")
    await _signup(client, "alice_search", "alice_search@example.com")
    bob_headers = await _login(client, "bob_search@example.com")
    alice_headers = await _login(client, "alice_search@example.com")
    await client.post("/posts", headers=bob_headers, json={"body": "unique pineapple essay"})

    found = await client.get("/search", params={"q": "bob_search"}, headers=alice_headers)
    assert found.status_code == 200
    assert "bob_search" in [item["handle"] for item in found.json()["users"]]

    posts = await client.get("/search", params={"q": "pineapple"}, headers=alice_headers)
    assert posts.status_code == 200
    assert any(item["body"] == "unique pineapple essay" for item in posts.json()["posts"])
    assert bob["id"]


@pytest.mark.asyncio
async def test_quote_and_repost_appear_in_following_feed(client: AsyncClient):
    bob = await _signup(client, "bob_rt", "bob_rt@example.com")
    await _signup(client, "alice_rt", "alice_rt@example.com")
    bob_headers = await _login(client, "bob_rt@example.com")
    alice_headers = await _login(client, "alice_rt@example.com")
    await client.post(f"/follows/{bob['id']}", headers=alice_headers)

    original = await client.post("/posts", headers=bob_headers, json={"body": "source tweet"})
    original_id = original.json()["id"]

    quoted = await client.post(
        "/posts",
        headers=alice_headers,
        json={"body": "my take", "quote_of_id": original_id},
    )
    assert quoted.status_code == 202

    reposted = await client.post(f"/posts/{original_id}/repost", headers=alice_headers)
    assert reposted.status_code == 202

    alice_profile = await client.get("/users/alice_rt/posts", headers=alice_headers)
    bodies = [item["body"] for item in alice_profile.json()["items"]]
    assert "my take" in bodies
    quote = next(item for item in alice_profile.json()["items"] if item["body"] == "my take")
    assert quote["quote_of"]["body"] == "source tweet"
    repost = next(item for item in alice_profile.json()["items"] if item["repost_of"] is not None)
    assert repost["repost_of"]["body"] == "source tweet"
    assert repost["reposted"] is True

    feed = await client.get("/feed/following", headers=alice_headers)
    feed_posts = [item for item in feed.json()["items"] if item["kind"] == "post"]
    assert any(item.get("quote_of") and item["quote_of"]["body"] == "source tweet" for item in feed_posts)
    assert any(item.get("repost_of") and item["repost_of"]["body"] == "source tweet" for item in feed_posts)

    unrt = await client.delete(f"/posts/{original_id}/repost", headers=alice_headers)
    assert unrt.status_code == 204


@pytest.mark.asyncio
async def test_delete_own_post_removes_it_from_profile(client: AsyncClient):
    await _signup(client, "solo_del", "solo_del@example.com")
    headers = await _login(client, "solo_del@example.com")
    posted = await client.post("/posts", headers=headers, json={"body": "delete me"})
    post_id = posted.json()["id"]
    deleted = await client.delete(f"/posts/{post_id}", headers=headers)
    assert deleted.status_code == 204
    profile = await client.get("/users/solo_del/posts", headers=headers)
    assert profile.json()["items"] == []


@pytest.mark.asyncio
async def test_feed_updates_detects_newer_posts(client: AsyncClient):
    bob = await _signup(client, "bob_peek", "bob_peek@example.com")
    await _signup(client, "alice_peek", "alice_peek@example.com")
    bob_headers = await _login(client, "bob_peek@example.com")
    alice_headers = await _login(client, "alice_peek@example.com")
    await client.post(f"/follows/{bob['id']}", headers=alice_headers)

    first = await client.post("/posts", headers=bob_headers, json={"body": "first peek"})
    feed = await client.get("/feed/following", headers=alice_headers)
    posts = [item for item in feed.json()["items"] if item["kind"] == "post"]
    since = posts[0]["created_at"]
    since_id = posts[0]["id"]

    before = await client.get(
        "/feed/updates",
        params={"surface": "following", "since": since, "since_id": since_id},
        headers=alice_headers,
    )
    assert before.status_code == 200
    assert before.json()["has_new"] is False

    await client.post("/posts", headers=bob_headers, json={"body": "second peek"})
    after = await client.get(
        "/feed/updates",
        params={"surface": "following", "since": since, "since_id": since_id},
        headers=alice_headers,
    )
    assert after.json()["has_new"] is True
    assert after.json()["count"] >= 1
    assert first.json()["id"]

    missing_since = await client.get("/feed/updates", headers=alice_headers)
    assert missing_since.json()["has_new"] is False


@pytest.mark.asyncio
async def test_search_popular_ranks_by_engagement(client: AsyncClient):
    await _signup(client, "bob_pop", "bob_pop@example.com")
    await _signup(client, "alice_pop", "alice_pop@example.com")
    await _signup(client, "carol_pop", "carol_pop@example.com")
    bob_headers = await _login(client, "bob_pop@example.com")
    alice_headers = await _login(client, "alice_pop@example.com")
    carol_headers = await _login(client, "carol_pop@example.com")

    loud = await client.post("/posts", headers=bob_headers, json={"body": "mango loud"})
    quiet = await client.post("/posts", headers=bob_headers, json={"body": "mango quiet"})
    await client.post(f"/likes/{loud.json()['id']}", headers=alice_headers)
    await client.post(f"/likes/{loud.json()['id']}", headers=carol_headers)

    popular = await client.get(
        "/search",
        params={"q": "mango", "scope": "posts", "sort": "popular"},
        headers=alice_headers,
    )
    bodies = [item["body"] for item in popular.json()["posts"]]
    assert bodies[0] == "mango loud"
    assert "mango quiet" in bodies
    assert popular.json()["users"] == []

    latest = await client.get(
        "/search",
        params={"q": "mango", "scope": "posts", "sort": "latest"},
        headers=alice_headers,
    )
    latest_bodies = [item["body"] for item in latest.json()["posts"]]
    assert set(latest_bodies) == {"mango loud", "mango quiet"}

    users_only = await client.get(
        "/search",
        params={"q": "bob_pop", "scope": "users"},
        headers=alice_headers,
    )
    assert users_only.json()["posts"] == []
    assert "bob_pop" in [item["handle"] for item in users_only.json()["users"]]
    assert quiet.json()["id"]
