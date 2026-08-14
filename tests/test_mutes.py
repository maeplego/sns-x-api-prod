from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.models import Follow, Post, User
from app.core.social_models import UserFeedEntry


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
async def test_muted_author_hidden_from_feed_until_unmuted(client: AsyncClient):
    bob = await _signup(client, "bob_mute", "bob_mute@example.com")
    alice = await _signup(client, "alice_mute", "alice_mute@example.com")
    alice_headers = {"Authorization": f"Bearer {await _login(client, 'alice_mute@example.com')}"}
    bob_headers = {"Authorization": f"Bearer {await _login(client, 'bob_mute@example.com')}"}

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "still following you"})

    before = await client.get("/feed", headers=alice_headers)
    assert len(before.json()["items"]) == 1

    muted = await client.post(f"/mutes/{bob['id']}", headers=alice_headers)
    assert muted.status_code == 201

    listed = await client.get("/mutes", headers=alice_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    after = await client.get("/feed", headers=alice_headers)
    assert len(after.json()["items"]) == 0

    async with database.SessionLocal() as db:
        follow = await db.scalar(
            select(Follow).where(
                Follow.follower_id == UUID(alice["id"]),
                Follow.followee_id == UUID(bob["id"]),
            )
        )
        assert follow is not None

    unmuted = await client.delete(f"/mutes/{bob['id']}", headers=alice_headers)
    assert unmuted.status_code == 204
    restored = await client.get("/feed", headers=alice_headers)
    assert len(restored.json()["items"]) == 1


@pytest.mark.asyncio
async def test_cannot_mute_self(client: AsyncClient):
    alice = await _signup(client, "alice_selfmute", "alice_selfmute@example.com")
    headers = {"Authorization": f"Bearer {await _login(client, 'alice_selfmute@example.com')}"}
    response = await client.post(f"/mutes/{alice['id']}", headers=headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_muted_keyword_hides_matching_post(client: AsyncClient):
    bob = await _signup(client, "bob_kw", "bob_kw@example.com")
    await _signup(client, "alice_kw", "alice_kw@example.com")
    alice_headers = {"Authorization": f"Bearer {await _login(client, 'alice_kw@example.com')}"}
    bob_headers = {"Authorization": f"Bearer {await _login(client, 'bob_kw@example.com')}"}

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "buy crypto now"})
    await client.post("/posts", headers=bob_headers, json={"body": "hello from bob"})

    created = await client.post(
        "/muted-keywords",
        headers=alice_headers,
        json={"keyword": "CRYPTO"},
    )
    assert created.status_code == 201
    assert created.json()["keyword"] == "crypto"

    listed = await client.get("/muted-keywords", headers=alice_headers)
    assert len(listed.json()) == 1

    feed = await client.get("/feed", headers=alice_headers)
    bodies = [item["body"] for item in feed.json()["items"]]
    assert "hello from bob" in bodies
    assert "buy crypto now" not in bodies


@pytest.mark.asyncio
async def test_own_posts_are_hidden_from_for_you(client: AsyncClient):
    await _signup(client, "solo", "solo@example.com")
    headers = {"Authorization": f"Bearer {await _login(client, 'solo@example.com')}"}
    await client.post("/posts", headers=headers, json={"body": "my own post"})

    feed = await client.get("/feed", headers=headers)
    assert feed.status_code == 200
    assert feed.json()["items"] == []


@pytest.mark.asyncio
async def test_posts_older_than_48_hours_hidden_from_feed(client: AsyncClient):
    bob = await _signup(client, "bob_old", "bob_old@example.com")
    await _signup(client, "alice_old", "alice_old@example.com")
    alice_headers = {"Authorization": f"Bearer {await _login(client, 'alice_old@example.com')}"}
    bob_headers = {"Authorization": f"Bearer {await _login(client, 'bob_old@example.com')}"}

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    posted = await client.post("/posts", headers=bob_headers, json={"body": "stale news"})
    post_id = posted.json()["id"]

    stale = datetime.now(UTC) - timedelta(hours=49)
    async with database.SessionLocal() as db:
        post = await db.get(Post, UUID(post_id))
        assert post is not None
        post.created_at = stale
        alice = await db.scalar(select(User).where(User.handle == "alice_old"))
        assert alice is not None
        entry = await db.scalar(
            select(UserFeedEntry).where(
                UserFeedEntry.user_id == alice.id,
                UserFeedEntry.post_id == post.id,
            )
        )
        assert entry is not None
        entry.created_at = stale
        await db.commit()

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.json()["items"] == []
