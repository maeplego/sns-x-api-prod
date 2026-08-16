import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core import database
from app.core.models import PostVisibility, User
from app.core.social_models import UserFeedEntry


@pytest.mark.asyncio
async def test_fanout_populates_user_feed_on_publish(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "bob_fan",
            "email": "bob_fan@example.com",
            "password": "password123",
            "display_name": "Bob",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "alice_fan",
            "email": "alice_fan@example.com",
            "password": "password123",
            "display_name": "Alice",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )

    bob_login = await client.post(
        "/auth/login",
        json={"email": "bob_fan@example.com", "password": "password123"},
    )
    alice_login = await client.post(
        "/auth/login",
        json={"email": "alice_fan@example.com", "password": "password123"},
    )
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

    async with database.SessionLocal() as db:
        bob = await db.scalar(select(User).where(User.handle == "bob_fan"))
        assert bob is not None

    await client.post(f"/follows/{bob.id}", headers=alice_headers)
    post = await client.post("/posts", headers=bob_headers, json={"body": "fanout me"})
    post_id = uuid.UUID(post.json()["id"])

    async with database.SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(UserFeedEntry))
        assert count == 2
        alice = await db.scalar(select(User).where(User.handle == "alice_fan"))
        assert alice is not None
        alice_entry = await db.scalar(
            select(UserFeedEntry).where(
                UserFeedEntry.user_id == alice.id,
                UserFeedEntry.post_id == post_id,
            )
        )
        bob_entry = await db.scalar(
            select(UserFeedEntry).where(
                UserFeedEntry.user_id == bob.id,
                UserFeedEntry.post_id == post_id,
            )
        )
        assert alice_entry is not None
        assert bob_entry is not None


@pytest.mark.asyncio
async def test_feed_reads_from_user_feed(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "bob_feed",
            "email": "bob_feed@example.com",
            "password": "password123",
            "display_name": "Bob",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "alice_feed",
            "email": "alice_feed@example.com",
            "password": "password123",
            "display_name": "Alice",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    bob_login = await client.post(
        "/auth/login",
        json={"email": "bob_feed@example.com", "password": "password123"},
    )
    alice_login = await client.post(
        "/auth/login",
        json={"email": "alice_feed@example.com", "password": "password123"},
    )
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

    async with database.SessionLocal() as db:
        bob = await db.scalar(select(User).where(User.handle == "bob_feed"))
        assert bob is not None

    await client.post(f"/follows/{bob.id}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "via thunder"})

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.status_code == 200
    assert len(feed.json()["items"]) == 1
    assert feed.json()["items"][0]["body"] == "via thunder"


@pytest.mark.asyncio
async def test_followers_only_fanout_excludes_non_followers(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "author_fo",
            "email": "author_fo@example.com",
            "password": "password123",
            "display_name": "Author",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "follower_fo",
            "email": "follower_fo@example.com",
            "password": "password123",
            "display_name": "Follower",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "stranger_fo",
            "email": "stranger_fo@example.com",
            "password": "password123",
            "display_name": "Stranger",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    author_login = await client.post(
        "/auth/login",
        json={"email": "author_fo@example.com", "password": "password123"},
    )
    follower_login = await client.post(
        "/auth/login",
        json={"email": "follower_fo@example.com", "password": "password123"},
    )
    author_headers = {"Authorization": f"Bearer {author_login.json()['access_token']}"}
    follower_headers = {"Authorization": f"Bearer {follower_login.json()['access_token']}"}

    async with database.SessionLocal() as db:
        author = await db.scalar(select(User).where(User.handle == "author_fo"))
        follower = await db.scalar(select(User).where(User.handle == "follower_fo"))
        stranger = await db.scalar(select(User).where(User.handle == "stranger_fo"))
        assert author and follower and stranger
        author_id = author.id
        follower_id = follower.id
        stranger_id = stranger.id

    await client.post(f"/follows/{author_id}", headers=follower_headers)
    post = await client.post(
        "/posts",
        headers=author_headers,
        json={"body": "followers only", "visibility": PostVisibility.FOLLOWERS_ONLY.value},
    )
    post_id = uuid.UUID(post.json()["id"])

    async with database.SessionLocal() as db:
        follower_entry = await db.scalar(
            select(UserFeedEntry).where(
                UserFeedEntry.user_id == follower_id,
                UserFeedEntry.post_id == post_id,
            )
        )
        stranger_entry = await db.scalar(
            select(UserFeedEntry).where(
                UserFeedEntry.user_id == stranger_id,
                UserFeedEntry.post_id == post_id,
            )
        )
        assert follower_entry is not None
        assert stranger_entry is None
