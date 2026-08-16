import uuid

import pytest
from httpx import AsyncClient

from app.core import database
from app.core.models import Post, PostEngagement, PostStatus


@pytest.mark.asyncio
async def test_create_post_returns_202_and_publishes(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={
            "handle": "poster",
            "email": "poster@example.com",
            "password": "password123",
            "display_name": "Poster",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    login = await client.post(
        "/auth/login",
        json={"email": "poster@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(
        "/posts",
        headers=headers,
        json={"body": "async publish me"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "processing"

    body = response.json()
    async with database.SessionLocal() as db:
        post = await db.get(Post, uuid.UUID(body["id"]))
        assert post is not None
        assert post.status == PostStatus.PUBLISHED
        engagement = await db.get(PostEngagement, uuid.UUID(body["id"]))
        assert engagement is not None
        assert engagement.like_count == 0

    public_get = await client.get(f"/posts/{body['id']}")
    assert public_get.status_code == 200
