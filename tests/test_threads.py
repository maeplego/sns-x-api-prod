from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.models import PostEngagement
from app.core.social_models import Notification


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
async def test_reply_sets_parent_and_root_and_appears_in_thread(client: AsyncClient):
    bob = await _signup(client, "bob_th", "bob_th@example.com")
    await _signup(client, "carol_th", "carol_th@example.com")
    bob_headers = await _login(client, "bob_th@example.com")
    carol_headers = await _login(client, "carol_th@example.com")

    root = await client.post("/posts", headers=bob_headers, json={"body": "root post"})
    root_id = root.json()["id"]

    reply = await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "a reply", "parent_id": root_id},
    )
    assert reply.status_code == 202
    reply_id = reply.json()["id"]

    fetched = await client.get(f"/posts/{reply_id}", headers=carol_headers)
    assert fetched.status_code == 200
    assert fetched.json()["parent_id"] == root_id
    assert fetched.json()["root_id"] == root_id

    nested = await client.post(
        "/posts",
        headers=bob_headers,
        json={"body": "nested", "parent_id": reply_id},
    )
    nested_id = nested.json()["id"]
    nested_fetched = await client.get(f"/posts/{nested_id}", headers=bob_headers)
    assert nested_fetched.json()["parent_id"] == reply_id
    assert nested_fetched.json()["root_id"] == root_id

    thread = await client.get(f"/posts/{reply_id}/thread", headers=carol_headers)
    assert thread.status_code == 200
    bodies = [item["body"] for item in thread.json()["items"]]
    assert bodies[0] == "root post"
    assert set(bodies) == {"root post", "a reply", "nested"}
    assert thread.json()["root_id"] == root_id

    profile = await client.get("/users/carol_th/posts")
    assert [item["body"] for item in profile.json()["items"]] == []
    replies = await client.get("/users/carol_th/posts", params={"tab": "replies"})
    assert [item["body"] for item in replies.json()["items"]] == ["a reply"]
    assert replies.json()["items"][0]["parent_author_handle"] == "bob_th"


@pytest.mark.asyncio
async def test_reply_increments_count_and_notifies_parent_author(client: AsyncClient):
    bob = await _signup(client, "bob_nt", "bob_nt@example.com")
    await _signup(client, "carol_nt", "carol_nt@example.com")
    bob_headers = await _login(client, "bob_nt@example.com")
    carol_headers = await _login(client, "carol_nt@example.com")

    root = await client.post("/posts", headers=bob_headers, json={"body": "please reply"})
    root_id = UUID(root.json()["id"])
    reply = await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "hi bob", "parent_id": str(root_id)},
    )
    reply_id = reply.json()["id"]

    async with database.SessionLocal() as db:
        engagement = await db.get(PostEngagement, root_id)
        assert engagement is not None
        assert engagement.reply_count == 1
        notes = list(
            (
                await db.execute(
                    select(Notification).where(Notification.user_id == UUID(bob["id"]))
                )
            ).scalars().all()
        )
        replied = [n for n in notes if n.type == "post_replied"]
        assert len(replied) == 1
        assert replied[0].payload_json["reply_id"] == reply_id

    notifications = await client.get("/notifications", headers=bob_headers)
    types = [item["type"] for item in notifications.json()["items"]]
    assert "post_replied" in types


@pytest.mark.asyncio
async def test_cannot_reply_to_missing_parent(client: AsyncClient):
    await _signup(client, "alice_miss", "alice_miss@example.com")
    headers = await _login(client, "alice_miss@example.com")
    response = await client.post(
        "/posts",
        headers=headers,
        json={"body": "orphan", "parent_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feed_dedupes_reply_when_root_is_present(client: AsyncClient):
    bob = await _signup(client, "bob_dd", "bob_dd@example.com")
    carol = await _signup(client, "carol_dd", "carol_dd@example.com")
    await _signup(client, "alice_dd", "alice_dd@example.com")
    bob_headers = await _login(client, "bob_dd@example.com")
    carol_headers = await _login(client, "carol_dd@example.com")
    alice_headers = await _login(client, "alice_dd@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post(f"/follows/{carol['id']}", headers=alice_headers)
    root = await client.post("/posts", headers=bob_headers, json={"body": "conversation root"})
    await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "conversation reply", "parent_id": root.json()["id"]},
    )

    feed = await client.get("/feed", headers=alice_headers)
    bodies = [item["body"] for item in feed.json()["items"]]
    assert "conversation root" in bodies
    assert "conversation reply" not in bodies


@pytest.mark.asyncio
async def test_orphan_reply_appears_when_viewer_does_not_follow_root_author(client: AsyncClient):
    await _signup(client, "bob_or", "bob_or@example.com")
    carol = await _signup(client, "carol_or", "carol_or@example.com")
    await _signup(client, "alice_or", "alice_or@example.com")
    bob_headers = await _login(client, "bob_or@example.com")
    carol_headers = await _login(client, "carol_or@example.com")
    alice_headers = await _login(client, "alice_or@example.com")

    await client.post(f"/follows/{carol['id']}", headers=alice_headers)
    root = await client.post("/posts", headers=bob_headers, json={"body": "unfollowed root"})
    await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "orphan reply", "parent_id": root.json()["id"]},
    )

    feed = await client.get("/feed", headers=alice_headers)
    items = feed.json()["items"]
    assert [item["body"] for item in items] == ["orphan reply"]
    assert items[0]["parent_id"] == root.json()["id"]


@pytest.mark.asyncio
async def test_reply_to_blocked_parent_author_is_dropped_from_feed(client: AsyncClient):
    bob = await _signup(client, "bob_bl", "bob_bl@example.com")
    carol = await _signup(client, "carol_bl", "carol_bl@example.com")
    await _signup(client, "alice_bl", "alice_bl@example.com")
    bob_headers = await _login(client, "bob_bl@example.com")
    carol_headers = await _login(client, "carol_bl@example.com")
    alice_headers = await _login(client, "alice_bl@example.com")

    await client.post(f"/follows/{carol['id']}", headers=alice_headers)
    await client.post(f"/blocks/{bob['id']}", headers=alice_headers)
    root = await client.post("/posts", headers=bob_headers, json={"body": "blocked author"})
    await client.post(
        "/posts",
        headers=carol_headers,
        json={"body": "reply to blocked", "parent_id": root.json()["id"]},
    )

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.json()["items"] == []
