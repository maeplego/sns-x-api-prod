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


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_under_the_hood_reports_nsfw_label(client: AsyncClient):
    await _signup(client, "bob_uth", "bob_uth@example.com")
    headers = await _login(client, "bob_uth@example.com")
    posted = await client.post("/posts", headers=headers, json={"body": "this is nsfw content"})
    assert posted.status_code == 202

    report = await client.get("/under-the-hood", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert "cred_score" in body
    assert body["post_label_counts"].get("nsfw", 0) >= 1
    assert any(item["label"] == "nsfw" for item in body["recent_post_labels"])
    assert "フォロー外" in body["summary"] or "cred" in body["summary"]
