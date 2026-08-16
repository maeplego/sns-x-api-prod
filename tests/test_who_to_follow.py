import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.models import User, UserStatus


async def _signup(client: AsyncClient, handle: str, email: str) -> dict:
    response = await client.post(
        "/auth/signup",
        json={
            "handle": handle,
            "email": email,
            "password": "password123",
            "display_name": handle.title(),
            "birthdate": "1990-01-01", "accept_terms": True,
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


async def _graph(client: AsyncClient) -> dict:
    """Alice follows Bob and Dana. Bob follows Carol. Dana follows Carol and Eve."""
    alice = await _signup(client, "alice_wtf", "alice_wtf@example.com")
    bob = await _signup(client, "bob_wtf", "bob_wtf@example.com")
    carol = await _signup(client, "carol_wtf", "carol_wtf@example.com")
    dana = await _signup(client, "dana_wtf", "dana_wtf@example.com")
    eve = await _signup(client, "eve_wtf", "eve_wtf@example.com")
    alice_headers = await _login(client, "alice_wtf@example.com")
    bob_headers = await _login(client, "bob_wtf@example.com")
    dana_headers = await _login(client, "dana_wtf@example.com")
    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post(f"/follows/{dana['id']}", headers=alice_headers)
    await client.post(f"/follows/{carol['id']}", headers=bob_headers)
    await client.post(f"/follows/{carol['id']}", headers=dana_headers)
    await client.post(f"/follows/{eve['id']}", headers=dana_headers)
    return {
        "alice": alice,
        "bob": bob,
        "carol": carol,
        "dana": dana,
        "eve": eve,
        "alice_headers": alice_headers,
        "bob_headers": bob_headers,
    }


@pytest.mark.asyncio
async def test_who_to_follow_ranks_friends_of_friends(client: AsyncClient):
    graph = await _graph(client)

    response = await client.get("/who-to-follow", headers=graph["alice_headers"])
    assert response.status_code == 200
    handles = [user["handle"] for user in response.json()["users"]]
    assert handles == ["carol_wtf", "eve_wtf"]
    users = response.json()["users"]
    assert users[0]["mutual_follow_count"] == 2
    assert users[0]["reason"] == "mutual_follows"
    assert users[1]["mutual_follow_count"] == 1


@pytest.mark.asyncio
async def test_who_to_follow_excludes_already_following(client: AsyncClient):
    graph = await _graph(client)
    await client.post(f"/follows/{graph['carol']['id']}", headers=graph["alice_headers"])

    response = await client.get("/who-to-follow", headers=graph["alice_headers"])
    handles = [user["handle"] for user in response.json()["users"]]
    assert handles == ["eve_wtf"]


@pytest.mark.asyncio
async def test_who_to_follow_excludes_blocked_and_muted(client: AsyncClient):
    graph = await _graph(client)
    await client.post(f"/blocks/{graph['carol']['id']}", headers=graph["alice_headers"])
    await client.post(f"/mutes/{graph['eve']['id']}", headers=graph["alice_headers"])

    response = await client.get("/who-to-follow", headers=graph["alice_headers"])
    assert response.json()["users"] == []


@pytest.mark.asyncio
async def test_feed_inserts_who_to_follow_at_sixth_slot(client: AsyncClient):
    graph = await _graph(client)
    for i in range(6):
        await client.post(
            "/posts",
            headers=graph["bob_headers"],
            json={"body": f"bob post {i}"},
        )

    feed = await client.get("/feed", headers=graph["alice_headers"])
    items = feed.json()["items"]
    kinds = [item["kind"] for item in items]
    assert kinds[5] == "who_to_follow"
    assert kinds.count("post") == 6
    assert kinds.count("who_to_follow") == 1
    assert [user["handle"] for user in items[5]["users"]] == ["carol_wtf", "eve_wtf"]

    following = await client.get("/feed/following", headers=graph["alice_headers"])
    following_kinds = [item["kind"] for item in following.json()["items"]]
    assert following_kinds[5] == "who_to_follow"


@pytest.mark.asyncio
async def test_who_to_follow_not_repeated_on_next_page(client: AsyncClient):
    graph = await _graph(client)
    for i in range(4):
        await client.post(
            "/posts",
            headers=graph["bob_headers"],
            json={"body": f"page post {i}"},
        )

    first = await client.get("/feed", headers=graph["alice_headers"], params={"limit": 2})
    assert any(item["kind"] == "who_to_follow" for item in first.json()["items"])
    cursor = first.json()["next_cursor"]
    assert cursor is not None

    second = await client.get(
        "/feed",
        headers=graph["alice_headers"],
        params={"limit": 2, "cursor": cursor},
    )
    assert all(item["kind"] == "post" for item in second.json()["items"])


@pytest.mark.asyncio
async def test_who_to_follow_skips_private_and_suspended(client: AsyncClient):
    graph = await _graph(client)

    async with database.SessionLocal() as db:
        carol = await db.scalar(select(User).where(User.handle == "carol_wtf"))
        eve = await db.scalar(select(User).where(User.handle == "eve_wtf"))
        assert carol is not None
        assert eve is not None
        carol.is_private = True
        eve.status = UserStatus.SUSPENDED
        await db.commit()

    response = await client.get("/who-to-follow", headers=graph["alice_headers"])
    assert response.json()["users"] == []
