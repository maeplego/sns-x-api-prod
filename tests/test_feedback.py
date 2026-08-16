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
            "birthdate": "1990-01-01", "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_hide_removes_that_post_but_keeps_the_author(client: AsyncClient):
    bob = await _signup(client, "bob_hide", "bob_hide@example.com")
    await _signup(client, "alice_hide", "alice_hide@example.com")
    bob_headers = await _headers(client, "bob_hide@example.com")
    alice_headers = await _headers(client, "alice_hide@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    first = await client.post("/posts", headers=bob_headers, json={"body": "hide me"})
    second = await client.post("/posts", headers=bob_headers, json={"body": "keep me"})

    hidden = await client.post(
        f"/feedback/{first.json()['id']}",
        headers=alice_headers,
        json={"kind": "hide"},
    )
    assert hidden.status_code == 201
    assert hidden.json()["kind"] == "hide"

    feed = await client.get("/feed", headers=alice_headers)
    bodies = [item["body"] for item in feed.json()["items"]]
    assert "keep me" in bodies
    assert "hide me" not in bodies

    listed = await client.get("/feedback", headers=alice_headers)
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/feedback/{first.json()['id']}", headers=alice_headers)
    assert deleted.status_code == 204
    restored = await client.get("/feed", headers=alice_headers)
    assert {item["body"] for item in restored.json()["items"]} == {"hide me", "keep me"}


@pytest.mark.asyncio
async def test_not_interested_hides_post_and_penalizes_author(client: AsyncClient):
    bob = await _signup(client, "bob_ni", "bob_ni@example.com")
    carol = await _signup(client, "carol_ni", "carol_ni@example.com")
    await _signup(client, "alice_ni", "alice_ni@example.com")
    bob_headers = await _headers(client, "bob_ni@example.com")
    carol_headers = await _headers(client, "carol_ni@example.com")
    alice_headers = await _headers(client, "alice_ni@example.com")

    await client.post(f"/follows/{bob['id']}", headers=alice_headers)
    await client.post(f"/follows/{carol['id']}", headers=alice_headers)
    disliked = await client.post("/posts", headers=bob_headers, json={"body": "bob disliked"})
    await client.post("/posts", headers=bob_headers, json={"body": "bob remaining"})
    await client.post("/posts", headers=carol_headers, json={"body": "carol post"})

    response = await client.post(
        f"/feedback/{disliked.json()['id']}",
        headers=alice_headers,
        json={"kind": "not_interested"},
    )
    assert response.status_code == 201

    feed = await client.get("/feed", headers=alice_headers)
    bodies = [item["body"] for item in feed.json()["items"]]
    assert "bob disliked" not in bodies
    assert "bob remaining" in bodies
    assert "carol post" in bodies
    assert bodies.index("carol post") < bodies.index("bob remaining")


@pytest.mark.asyncio
async def test_cannot_feedback_own_post(client: AsyncClient):
    await _signup(client, "solo_fb", "solo_fb@example.com")
    headers = await _headers(client, "solo_fb@example.com")
    posted = await client.post("/posts", headers=headers, json={"body": "mine"})
    # own posts can appear on For You; hiding yourself is still rejected
    response = await client.post(
        f"/feedback/{posted.json()['id']}",
        headers=headers,
        json={"kind": "hide"},
    )
    assert response.status_code == 400
