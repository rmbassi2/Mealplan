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

        # Verify option card fields and taxonomy badges
        for option in data["options"]:
            assert "id" in option
            assert "name" in option
            assert "description" in option
            assert "totalTime" in option
            assert "imageUrl" in option
            assert "badges" in option
            assert isinstance(option["badges"], list)
            assert option["imageUrl"].startswith("/api/recipe-image/")


@pytest.mark.anyio
async def test_taxonomy_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/taxonomy")
        assert resp.status_code == 200
        data = resp.json()
        assert "moods" in data
        mood_ids = [m["id"] for m in data["moods"]]
        assert "surprise" in mood_ids
        assert "quick" in mood_ids
        assert "chicken" in mood_ids


@pytest.mark.anyio
async def test_get_options_with_filters():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Quick mood
        resp = await client.get("/api/options?mood=quick")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["options"]) > 0

        # 2. Chicken protein filter
        resp_chicken = await client.get("/api/options?protein=chicken")
        assert resp_chicken.status_code == 200
        data_chicken = resp_chicken.json()
        assert len(data_chicken["options"]) > 0
        for opt in data_chicken["options"]:
            assert "chicken" in [t.lower() for t in opt.get("tags", [])]

        # 3. Sheet pan tool filter
        resp_tool = await client.get("/api/options?tool=sheet-pan")
        assert resp_tool.status_code == 200
        data_tool = resp_tool.json()
        assert len(data_tool["options"]) > 0

        # 4. Italian cuisine filter
        resp_cuisine = await client.get("/api/options?cuisine=italian")
        assert resp_cuisine.status_code == 200
        data_cuisine = resp_cuisine.json()
        assert len(data_cuisine["options"]) > 0


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
async def test_choose_external_recipe_url_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sample_url = "https://www.seriouseats.com/the-best-crispy-roast-potatoes-recipe"
        resp = await client.post(
            "/api/choose",
            json={"custom_note": f"Make this tonight: {sample_url}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["external_url"] == sample_url
        assert data["source_domain"] == "seriouseats.com"
        assert "Crispy Roast Potatoes" in data["dish_name"]
        assert data["emoji"] == "🌐"

        # Check /api/today reflects external URL
        today_resp = await client.get("/api/today")
        assert today_resp.status_code == 200
        today_data = today_resp.json()
        assert today_data["has_plan"] is True
        assert today_data["plan"]["external_url"] == sample_url
        assert today_data["plan"]["source_domain"] == "seriouseats.com"


@pytest.mark.anyio
async def test_url_info_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sample_url = "https://www.allrecipes.com/recipe/12345/homemade-chicken-pot-pie"
        resp = await client.get(f"/api/url-info?url={sample_url}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "allrecipes.com"
        assert "Chicken Pot Pie" in data["title"]


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
async def test_reset_today_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Submit a choice first
        await client.post("/api/choose", json={"recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01"})
        
        # Verify /api/today reports plan
        r1 = await client.get("/api/today")
        assert r1.json()["has_plan"] is True

        # Call reset
        reset_resp = await client.post("/api/reset-today")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "success"

        # Verify /api/today is now reset
        r2 = await client.get("/api/today")
        assert r2.json()["has_plan"] is False



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


def test_taxonomy_unit_logic():
    from app.taxonomy import extract_recipe_taxonomy, is_dinner_recipe, select_balanced_recipes

    sample_recipe = {
        "name": "Chicken Fajitas",
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"slug": "chicken"},
            {"slug": "skillet"},
            {"slug": "mexican-texmex"},
            {"slug": "quick-weeknight"},
        ],
    }

    tax = extract_recipe_taxonomy(sample_recipe)
    assert "dinner" in tax["categories"]
    assert "cast-iron-skillet" in tax["tools"]
    assert "chicken" in tax["tags"]
    assert tax["primary_protein"] == "chicken"
    assert is_dinner_recipe(tax) is True

    # Badges generated
    assert len(tax["badges"]) > 0
    badge_labels = [b["label"] for b in tax["badges"]]
    assert any("Cast Iron" in lbl or "Mexican" in lbl or "Quick" in lbl for lbl in badge_labels)

    # Balanced selection
    from app.mock_data import MOCK_RECIPES
    balanced = select_balanced_recipes(MOCK_RECIPES, count=3)
    assert len(balanced) == 3
    # Ensure distinct recipes
    assert len({r["id"] for r in balanced}) == 3


def test_url_helper_unit_logic():
    from app.url_helper import extract_url_from_text, clean_domain, clean_page_title, slug_to_title

    text = "Hey check this recipe out: https://www.seriouseats.com/the-best-crispy-roast-potatoes-recipe for tonight!"
    extracted = extract_url_from_text(text)
    assert extracted == "https://www.seriouseats.com/the-best-crispy-roast-potatoes-recipe"

    assert clean_domain(extracted) == "seriouseats.com"
    assert clean_domain("https://sub.domain.co.uk/path") == "sub.domain.co.uk"

    title = slug_to_title(extracted)
    assert "Crispy Roast Potatoes" in title

    raw_title = "Crispy Honey Garlic Salmon Recipe | Serious Eats"
    cleaned = clean_page_title(raw_title)
    assert "Serious Eats" not in cleaned
    assert "Crispy Honey Garlic Salmon" in cleaned
