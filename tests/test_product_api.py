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
            "accept_terms": True,
            "accept_privacy": True,
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
async def test_public_profile_omits_email(client: AsyncClient):
    await _signup(client, "bob_pub", "bob_pub@example.com")
    profile = await client.get("/users/bob_pub")
    assert profile.status_code == 200
    body = profile.json()
    assert "email" not in body
    assert body["handle"] == "bob_pub"
    assert body["follower_count"] == 0
    assert body["following_count"] == 0
    assert body["is_following"] is False


@pytest.mark.asyncio
async def test_profile_block_and_mute_actions(client: AsyncClient):
    bob = await _signup(client, "bob_act", "bob_act@example.com")
    await _signup(client, "alice_act", "alice_act@example.com")
    alice_headers = await _login(client, "alice_act@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    muted = await client.post(f"/mutes/{bob['id']}", headers=alice_headers)
    assert muted.status_code == 201
    muted_profile = await client.get("/users/bob_act", headers=alice_headers)
    assert muted_profile.json()["is_muting"] is True
    assert muted_profile.json()["is_following"] is True

    blocked = await client.post(f"/blocks/{bob['id']}", headers=alice_headers)
    assert blocked.status_code == 201
    blocked_profile = await client.get("/users/bob_act", headers=alice_headers)
    assert blocked_profile.json()["is_blocking"] is True
    assert blocked_profile.json()["is_following"] is False
    assert blocked_profile.json()["follower_count"] == 0

    follow_again = await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    assert follow_again.status_code == 400

    await client.delete(f"/blocks/{bob['id']}", headers=alice_headers)
    await client.delete(f"/mutes/{bob['id']}", headers=alice_headers)
    cleared = await client.get("/users/bob_act", headers=alice_headers)
    assert cleared.json()["is_blocking"] is False
    assert cleared.json()["is_muting"] is False


@pytest.mark.asyncio
async def test_patch_me_updates_profile(client: AsyncClient):
    await _signup(client, "alice_me", "alice_me@example.com")
    headers = await _login(client, "alice_me@example.com")
    updated = await client.patch(
        "/users/me",
        headers=headers,
        json={"display_name": "Alice Updated", "bio": "hello"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Alice Updated"
    assert updated.json()["bio"] == "hello"
    assert updated.json()["email"] == "alice_me@example.com"


@pytest.mark.asyncio
async def test_follow_lists_and_counts(client: AsyncClient):
    bob = await _signup(client, "bob_list", "bob_list@example.com")
    await _signup(client, "alice_list", "alice_list@example.com")
    alice_headers = await _login(client, "alice_list@example.com")
    await client.post(f"/follows/{bob['id']}", headers=alice_headers)

    profile = await client.get("/users/bob_list", headers=alice_headers)
    assert profile.json()["follower_count"] == 1
    assert profile.json()["is_following"] is True

    followers = await client.get("/users/bob_list/followers", headers=alice_headers)
    assert [item["handle"] for item in followers.json()["items"]] == ["alice_list"]

    following = await client.get("/users/alice_list/following", headers=alice_headers)
    assert [item["handle"] for item in following.json()["items"]] == ["bob_list"]


@pytest.mark.asyncio
async def test_follow_backfills_existing_posts_into_following_feed(client: AsyncClient):
    bob = await _signup(client, "bob_bf", "bob_bf@example.com")
    await _signup(client, "alice_bf", "alice_bf@example.com")
    bob_headers = await _login(client, "bob_bf@example.com")
    alice_headers = await _login(client, "alice_bf@example.com")

    await client.post("/posts", headers=bob_headers, json={"body": "already published"})
    before = await client.get("/feed/following", headers=alice_headers)
    assert before.json()["items"] == []

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    after = await client.get("/feed/following", headers=alice_headers)
    bodies = [item["body"] for item in after.json()["items"] if item["kind"] == "post"]
    assert bodies == ["already published"]


@pytest.mark.asyncio
async def test_mark_notifications_read(client: AsyncClient):
    await _signup(client, "bob_rd", "bob_rd@example.com")
    await _signup(client, "alice_rd", "alice_rd@example.com")
    bob_headers = await _login(client, "bob_rd@example.com")
    alice_headers = await _login(client, "alice_rd@example.com")

    post = await client.post("/posts", headers=bob_headers, json={"body": "like this"})
    await client.post(f"/likes/{post.json()['id']}", headers=alice_headers)

    listed = await client.get("/notifications", headers=bob_headers)
    assert listed.json()["unread_count"] == 1

    marked = await client.post("/notifications/read", headers=bob_headers)
    assert marked.json()["updated"] == 1

    after = await client.get("/notifications", headers=bob_headers)
    assert after.json()["unread_count"] == 0
    assert after.json()["items"][0]["read_at"] is not None


@pytest.mark.asyncio
async def test_like_notifications_from_same_user_are_grouped(client: AsyncClient):
    await _signup(client, "bob_grp", "bob_grp@example.com")
    await _signup(client, "alice_grp", "alice_grp@example.com")
    bob_headers = await _login(client, "bob_grp@example.com")
    alice_headers = await _login(client, "alice_grp@example.com")

    first = await client.post("/posts", headers=bob_headers, json={"body": "first liked"})
    second = await client.post("/posts", headers=bob_headers, json={"body": "second liked"})
    await client.post(f"/likes/{first.json()['id']}", headers=alice_headers)
    await client.post(f"/likes/{second.json()['id']}", headers=alice_headers)

    listed = await client.get("/notifications", headers=bob_headers)
    likes = [item for item in listed.json()["items"] if item["type"] == "post_liked"]
    assert len(likes) == 1
    bodies = {post["body"] for post in likes[0]["payload_json"]["posts"]}
    assert bodies == {"first liked", "second liked"}
    assert listed.json()["unread_count"] == 2


@pytest.mark.asyncio
async def test_profile_likes_are_private_to_self(client: AsyncClient):
    bob = await _signup(client, "bob_lk", "bob_lk@example.com")
    await _signup(client, "alice_lk", "alice_lk@example.com")
    bob_headers = await _login(client, "bob_lk@example.com")
    alice_headers = await _login(client, "alice_lk@example.com")

    post = await client.post("/posts", headers=bob_headers, json={"body": "likeable"})
    await client.post(f"/likes/{post.json()['id']}", headers=alice_headers)

    own = await client.get("/users/alice_lk/likes", headers=alice_headers)
    assert own.status_code == 200
    assert [item["body"] for item in own.json()["items"]] == ["likeable"]

    other = await client.get("/users/alice_lk/likes", headers=bob_headers)
    assert other.status_code == 403
    assert bob["id"]


@pytest.mark.asyncio
async def test_cors_allows_vite_origin(client: AsyncClient):
    response = await client.get("/health", headers={"Origin": "http://localhost:5175"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5175"
