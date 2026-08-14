import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import database
from app.core.embedding_models import PostEmbedding
from app.core.models import User

TOPIC = "python async tutorial for beginners"


@pytest.mark.asyncio
async def test_oon_post_appears_in_feed(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "alice_oon",
            "email": "alice_oon@example.com",
            "password": "password123",
            "display_name": "Alice",
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "bob_oon",
            "email": "bob_oon@example.com",
            "password": "password123",
            "display_name": "Bob",
        },
    )
    await client.post(
        "/auth/signup",
        json={
            "handle": "carol_oon",
            "email": "carol_oon@example.com",
            "password": "password123",
            "display_name": "Carol",
        },
    )

    alice_login = await client.post(
        "/auth/login",
        json={"email": "alice_oon@example.com", "password": "password123"},
    )
    bob_login = await client.post(
        "/auth/login",
        json={"email": "bob_oon@example.com", "password": "password123"},
    )
    carol_login = await client.post(
        "/auth/login",
        json={"email": "carol_oon@example.com", "password": "password123"},
    )
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}
    carol_headers = {"Authorization": f"Bearer {carol_login.json()['access_token']}"}

    async with database.SessionLocal() as db:
        bob = await db.scalar(select(User).where(User.handle == "bob_oon"))
        assert bob is not None

    await client.post(f"/follows/{bob.id}", headers=alice_headers)
    await client.post("/posts", headers=bob_headers, json={"body": TOPIC})
    carol_post = await client.post("/posts", headers=carol_headers, json={"body": TOPIC})
    carol_post_id = uuid.UUID(carol_post.json()["id"])

    async with database.SessionLocal() as db:
        embedding = await db.scalar(
            select(PostEmbedding).where(PostEmbedding.post_id == carol_post_id)
        )
        assert embedding is not None

    feed = await client.get("/feed", headers=alice_headers)
    assert feed.status_code == 200
    bodies = {item["body"] for item in feed.json()["items"]}
    assert TOPIC in bodies
    assert len(feed.json()["items"]) >= 2


@pytest.mark.asyncio
async def test_embedding_created_on_publish(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "embed_user",
            "email": "embed_user@example.com",
            "password": "password123",
            "display_name": "Embed",
        },
    )
    login = await client.post(
        "/auth/login",
        json={"email": "embed_user@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    post = await client.post("/posts", headers=headers, json={"body": "embedding test"})
    post_id = uuid.UUID(post.json()["id"])

    async with database.SessionLocal() as db:
        row = await db.scalar(select(PostEmbedding).where(PostEmbedding.post_id == post_id))
        assert row is not None
        assert len(row.embedding) == 384
