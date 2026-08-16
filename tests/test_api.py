import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_login_and_post(client: AsyncClient):
    signup = await client.post(
        "/auth/signup",
        json={
            "handle": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "display_name": "Alice",
            "birthdate": "1990-01-01", "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert signup.status_code == 201

    signup_b = await client.post(
        "/auth/signup",
        json={
            "handle": "bob",
            "email": "bob@example.com",
            "password": "password123",
            "display_name": "Bob",
            "birthdate": "1990-01-01", "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert signup_b.status_code == 201
    bob_headers = {"Authorization": f"Bearer {signup_b.json()['access_token']}"}
    bob_me = await client.get("/users/me", headers=bob_headers)
    bob_id = bob_me.json()["id"]

    login = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["handle"] == "alice"

    follow = await client.post(f"/follows/{bob_id}", headers=headers)
    assert follow.status_code == 201

    post = await client.post(
        "/posts",
        headers=headers,
        json={"body": "hello sns-tutorial-x"},
    )
    assert post.status_code == 202
    assert post.json()["status"] == "processing"
    post_id = post.json()["id"]

    published = await client.get(f"/posts/{post_id}", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["body"] == "hello sns-tutorial-x"

    posts = await client.get("/users/alice/posts")
    assert posts.status_code == 200
    assert len(posts.json()["items"]) == 1


@pytest.mark.asyncio
async def test_create_post_requires_auth(client: AsyncClient):
    response = await client.post("/posts", json={"body": "no auth"})
    assert response.status_code == 401
