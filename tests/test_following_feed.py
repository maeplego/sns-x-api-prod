from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.embedding_models import PostEmbedding
from app.core.models import Post, User
from app.core.social_models import UserFeedEntry

TOPIC = "python async tutorial for beginners"


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
async def test_following_shows_followed_posts_newest_first(client: AsyncClient):
    bob = await _signup(client, "bob_flw", "bob_flw@example.com")
    await _signup(client, "alice_flw", "alice_flw@example.com")
    alice_headers = await _login(client, "alice_flw@example.com")
    bob_headers = await _login(client, "bob_flw@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    older = await client.post("/posts", headers=bob_headers, json={"body": "older following post"})
    newer = await client.post("/posts", headers=bob_headers, json={"body": "newer following post"})

    older_time = datetime.now(UTC) - timedelta(minutes=2)
    newer_time = datetime.now(UTC) - timedelta(minutes=1)
    async with database.SessionLocal() as db:
        alice = await db.scalar(select(User).where(User.handle == "alice_flw"))
        assert alice is not None
        for post_id, when in ((older.json()["id"], older_time), (newer.json()["id"], newer_time)):
            post = await db.get(Post, UUID(post_id))
            assert post is not None
            post.created_at = when
            entry = await db.scalar(
                select(UserFeedEntry).where(
                    UserFeedEntry.user_id == alice.id,
                    UserFeedEntry.post_id == post.id,
                )
            )
            assert entry is not None
            entry.created_at = when
        await db.commit()

    feed = await client.get("/feed/following", headers=alice_headers)
    assert feed.status_code == 200
    body = feed.json()
    assert body["surface"] == "following"
    assert [item["body"] for item in body["items"]] == [
        "newer following post",
        "older following post",
    ]
    assert all(item["rank_score"] is None for item in body["items"])


@pytest.mark.asyncio
async def test_following_excludes_out_of_network_posts(client: AsyncClient):
    bob = await _signup(client, "bob_flw_oon", "bob_flw_oon@example.com")
    await _signup(client, "carol_flw_oon", "carol_flw_oon@example.com")
    await _signup(client, "alice_flw_oon", "alice_flw_oon@example.com")
    alice_headers = await _login(client, "alice_flw_oon@example.com")
    bob_headers = await _login(client, "bob_flw_oon@example.com")
    carol_headers = await _login(client, "carol_flw_oon@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    bob_post = await client.post("/posts", headers=bob_headers, json={"body": TOPIC})
    carol_post = await client.post("/posts", headers=carol_headers, json={"body": TOPIC})
    carol_post_id = UUID(carol_post.json()["id"])

    async with database.SessionLocal() as db:
        embedding = await db.scalar(
            select(PostEmbedding).where(PostEmbedding.post_id == carol_post_id)
        )
        assert embedding is not None

    for_you = await client.get("/feed", headers=alice_headers)
    for_you_ids = {item["id"] for item in for_you.json()["items"]}
    assert bob_post.json()["id"] in for_you_ids
    assert carol_post.json()["id"] in for_you_ids
    assert for_you.json()["surface"] == "for_you"

    following = await client.get("/feed/following", headers=alice_headers)
    following_ids = {item["id"] for item in following.json()["items"]}
    assert bob_post.json()["id"] in following_ids
    assert carol_post.json()["id"] not in following_ids
    assert following.json()["surface"] == "following"


@pytest.mark.asyncio
async def test_following_shows_posts_older_than_48_hours(client: AsyncClient):
    bob = await _signup(client, "bob_flw_old", "bob_flw_old@example.com")
    await _signup(client, "alice_flw_old", "alice_flw_old@example.com")
    alice_headers = await _login(client, "alice_flw_old@example.com")
    bob_headers = await _login(client, "bob_flw_old@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    posted = await client.post("/posts", headers=bob_headers, json={"body": "stale following news"})
    post_id = posted.json()["id"]

    stale = datetime.now(UTC) - timedelta(hours=49)
    async with database.SessionLocal() as db:
        post = await db.get(Post, UUID(post_id))
        assert post is not None
        post.created_at = stale
        alice = await db.scalar(select(User).where(User.handle == "alice_flw_old"))
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

    for_you = await client.get("/feed", headers=alice_headers)
    assert for_you.json()["items"] == []

    following = await client.get("/feed/following", headers=alice_headers)
    assert [item["body"] for item in following.json()["items"]] == ["stale following news"]


@pytest.mark.asyncio
async def test_following_still_hides_muted_authors(client: AsyncClient):
    bob = await _signup(client, "bob_flw_mute", "bob_flw_mute@example.com")
    await _signup(client, "alice_flw_mute", "alice_flw_mute@example.com")
    alice_headers = await _login(client, "alice_flw_mute@example.com")
    bob_headers = await _login(client, "bob_flw_mute@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "muted on following"})
    await client.post(f"/mutes/{bob['id']}", headers=alice_headers)

    following = await client.get("/feed/following", headers=alice_headers)
    assert following.json()["items"] == []


@pytest.mark.asyncio
async def test_following_keeps_root_and_reply(client: AsyncClient):
    bob = await _signup(client, "bob_flw_dd", "bob_flw_dd@example.com")
    carol = await _signup(client, "carol_flw_dd", "carol_flw_dd@example.com")
    await _signup(client, "alice_flw_dd", "alice_flw_dd@example.com")
    bob_headers = await _login(client, "bob_flw_dd@example.com")
    carol_headers = await _login(client, "carol_flw_dd@example.com")
    alice_headers = await _login(client, "alice_flw_dd@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post(f"/follows/{carol['id']}", headers=alice_headers)
    root = await client.post("/posts", headers=bob_headers, json={"body": "following root"})
    reply = await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "following reply", "parent_id": root.json()["id"]},
    )

    root_time = datetime.now(UTC) - timedelta(minutes=2)
    reply_time = datetime.now(UTC) - timedelta(minutes=1)
    async with database.SessionLocal() as db:
        alice = await db.scalar(select(User).where(User.handle == "alice_flw_dd"))
        assert alice is not None
        for post_id, when in ((root.json()["id"], root_time), (reply.json()["id"], reply_time)):
            post = await db.get(Post, UUID(post_id))
            assert post is not None
            post.created_at = when
            entry = await db.scalar(
                select(UserFeedEntry).where(
                    UserFeedEntry.user_id == alice.id,
                    UserFeedEntry.post_id == post.id,
                )
            )
            assert entry is not None
            entry.created_at = when
        await db.commit()

    for_you = await client.get("/feed", headers=alice_headers)
    for_you_bodies = [item["body"] for item in for_you.json()["items"]]
    assert "following root" in for_you_bodies
    assert "following reply" not in for_you_bodies

    following = await client.get("/feed/following", headers=alice_headers)
    following_posts = [item for item in following.json()["items"] if item["kind"] == "post"]
    following_bodies = [item["body"] for item in following_posts]
    assert following_bodies == ["following reply", "following root"]
    reply_card = next(item for item in following_posts if item["body"] == "following reply")
    assert reply_card["parent_author_handle"] == "bob_flw_dd"
