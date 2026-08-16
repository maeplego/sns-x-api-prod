import pytest
from httpx import AsyncClient

from app.request.routers.trends import extract_hashtags


def test_extract_hashtags():
    assert extract_hashtags("Hello #Foo and #bar_1!") == {"foo", "bar_1"}
    assert extract_hashtags("no tags") == set()


@pytest.mark.asyncio
async def test_trends_endpoint(client: AsyncClient):
    signup = await client.post(
        "/auth/signup",
        json={
            "handle": "trenduser",
            "email": "trenduser@example.com",
            "password": "password123",
            "display_name": "Trend",
            "birthdate": "1990-01-01",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert signup.status_code == 201
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/posts",
        headers=headers,
        json={"body": "talking about #snsx and #feed"},
    )
    assert created.status_code in (201, 202)

    # Worker may be async; trends can still return empty until published.
    trends = await client.get("/trends", headers=headers)
    assert trends.status_code == 200
    body = trends.json()
    assert body["window_hours"] == 24
    assert "items" in body
