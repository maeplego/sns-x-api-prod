import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core import database
from app.core.social_models import FeedImpression, Notification


@pytest.mark.asyncio
async def test_feed_records_impressions(client: AsyncClient):
    bob_signup = await client.post(
        "/auth/signup",
        json={
            "handle": "bob_imp",
            "email": "bob_imp@example.com",
            "password": "password123",
            "display_name": "Bob",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "alice_imp",
            "email": "alice_imp@example.com",
            "password": "password123",
            "display_name": "Alice",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    bob_me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {bob_signup.json()['access_token']}"},
    )
    bob_id = bob_me.json()["id"]

    bob_login = await client.post(
        "/auth/login",
        json={"email": "bob_imp@example.com", "password": "password123"},
    )
    alice_login = await client.post(
        "/auth/login",
        json={"email": "alice_imp@example.com", "password": "password123"},
    )
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

    await client.post(f"/follows/{bob_id}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": "impression target"})

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.status_code == 200
    assert len(feed.json()["items"]) == 1
    assert "X-Request-ID" in feed.headers

    async with database.SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(FeedImpression))
        assert count == 1


@pytest.mark.asyncio
async def test_like_creates_notification(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "author_like",
            "email": "author_like@example.com",
            "password": "password123",
            "display_name": "Author",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "liker_like",
            "email": "liker_like@example.com",
            "password": "password123",
            "display_name": "Liker",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    author_login = await client.post(
        "/auth/login",
        json={"email": "author_like@example.com", "password": "password123"},
    )
    liker_login = await client.post(
        "/auth/login",
        json={"email": "liker_like@example.com", "password": "password123"},
    )
    author_headers = {"Authorization": f"Bearer {author_login.json()['access_token']}"}
    liker_headers = {"Authorization": f"Bearer {liker_login.json()['access_token']}"}

    post = await client.post("/posts", headers=author_headers, json={"body": "like me"})
    post_id = post.json()["id"]

    like = await client.post(f"/likes/{post_id}", headers=liker_headers)
    assert like.status_code == 201

    notifications = await client.get("/notifications", headers=author_headers)
    assert notifications.status_code == 200
    body = notifications.json()
    assert body["unread_count"] >= 1
    assert body["items"][0]["type"] == "post_liked"
    posts = body["items"][0]["payload_json"]["posts"]
    assert posts[0]["body"] == "like me"
    assert posts[0]["id"] == post_id

    async with database.SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(Notification))
        assert count == 1
