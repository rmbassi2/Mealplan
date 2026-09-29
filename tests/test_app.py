import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from app.mealie_client import format_recipe_time


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "mock_mode" in data


@pytest.mark.anyio
async def test_get_options_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/options")
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        assert len(data["options"]) == 3

        # Verify option card fields
        for option in data["options"]:
            assert "id" in option
            assert "name" in option
            assert "description" in option
            assert "totalTime" in option
            assert "imageUrl" in option
            assert option["imageUrl"].startswith("/api/recipe-image/")


@pytest.mark.anyio
async def test_get_recipe_image_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request image for a mock recipe
        resp = await client.get("/api/recipe-image/e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01")
        assert resp.status_code == 200
        assert "image/" in resp.headers.get("content-type", "")
        assert len(resp.content) > 0


@pytest.mark.anyio
async def test_choose_recipe_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/choose",
            json={"recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Meal plan updated" in data["message"]


@pytest.mark.anyio
async def test_choose_custom_note_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/choose",
            json={"custom_note": "Spicy Thai Green Curry Takeout"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Meal plan updated" in data["message"]


@pytest.mark.anyio
async def test_today_endpoint_returns_locked_in_choice():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First submit a choice
        choose_resp = await client.post(
            "/api/choose",
            json={"recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01"},
        )
        assert choose_resp.status_code == 200

        # Then query /api/today
        resp = await client.get("/api/today")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_plan"] is True
        assert data["plan"] is not None
        assert "Crispy Honey Garlic Salmon" in data["plan"]["dish_name"]
        assert data["plan"]["is_custom"] is False


@pytest.mark.anyio
async def test_cleanup_today_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/cleanup-today")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Cleaned up" in data["message"]


@pytest.mark.anyio
async def test_choose_validation_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Neither recipe_id nor custom_note provided
        resp = await client.post("/api/choose", json={})
        assert resp.status_code in (422, 400)


def test_time_formatting_helper():
    assert format_recipe_time({"totalTime": "PT45M"}) == "45 mins"
    assert format_recipe_time({"totalTime": "PT1H15M"}) == "1 hr 15 mins"
    assert format_recipe_time({"prepTime": "PT20M"}) == "20 mins"
    assert format_recipe_time({"totalTime": "35"}) == "35 mins"
    assert format_recipe_time({"performTime": "25 mins"}) == "25 mins"
    assert format_recipe_time({}) == "30 mins"
