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

        # 5. Skillet mood filter
        resp_skillet = await client.get("/api/options?mood=skillet")
        assert resp_skillet.status_code == 200
        data_skillet = resp_skillet.json()
        assert len(data_skillet["options"]) > 0

        # 6. One-pot mood filter
        resp_onepot = await client.get("/api/options?mood=one-pot")
        assert resp_onepot.status_code == 200
        data_onepot = resp_onepot.json()
        assert len(data_onepot["options"]) > 0

        # 7. Pork protein filter
        resp_pork = await client.get("/api/options?protein=pork")
        assert resp_pork.status_code == 200
        data_pork = resp_pork.json()
        assert len(data_pork["options"]) > 0

        # 8. Pasta mood filter
        resp_pasta = await client.get("/api/options?mood=pasta")
        assert resp_pasta.status_code == 200
        data_pasta = resp_pasta.json()
        assert len(data_pasta["options"]) > 0

        # 9. Asian cuisine filter
        resp_asian = await client.get("/api/options?cuisine=asian")
        assert resp_asian.status_code == 200
        data_asian = resp_asian.json()
        assert len(data_asian["options"]) > 0


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
async def test_get_side_options_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/side-options")
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        assert len(data["options"]) == 3
        first = data["options"][0]
        assert "id" in first
        assert "name" in first
        assert "totalTime" in first
        assert "imageUrl" in first


@pytest.mark.anyio
async def test_choose_with_side_dish_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/choose",
            json={
                "recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01",
                "side_recipe_id": "side-e4b1-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Crispy Honey Garlic Salmon" in data["dish_name"]
        assert "Garlic Butter Baby Potatoes" in data["side_name"]
        assert data["side_emoji"] == "🥔"

        # Verify /api/today reports both
        t_resp = await client.get("/api/today")
        assert t_resp.status_code == 200
        t_data = t_resp.json()
        assert t_data["has_plan"] is True
        assert t_data["plan"]["dish_name"] == data["dish_name"]
        assert t_data["plan"]["side_name"] == data["side_name"]



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


def test_taxonomy_overhaul_separation_and_diversity():
    """Verify overhauled taxonomy cleanly separates dinners vs sides and provides 3-bucket side diversity."""
    from app.taxonomy import (
        extract_recipe_taxonomy,
        is_dinner_recipe,
        is_side_recipe,
        classify_side_bucket,
        select_side_recipes,
    )

    # 1. Main dinner salads and potato dishes must NEVER be identified as sides
    dinner_salad = {
        "name": "Asian Noodle Salad with Chicken & Peanut Dressing",
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tags": [{"slug": "chicken"}, {"slug": "salad"}, {"slug": "quick-weeknight"}],
    }
    tax_ds = extract_recipe_taxonomy(dinner_salad)
    assert is_dinner_recipe(tax_ds) is True
    assert is_side_recipe(tax_ds, dinner_salad) is False

    dinner_burger = {
        "name": "Sweet Potato Black Bean Burger",
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tags": [{"slug": "vegan"}, {"slug": "beans-legumes"}, {"slug": "sandwich-wrap"}],
    }
    tax_db = extract_recipe_taxonomy(dinner_burger)
    assert is_dinner_recipe(tax_db) is True
    assert is_side_recipe(tax_db, dinner_burger) is False

    dinner_soup = {
        "name": "Potato-Leek Soup with Sage",
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}, {"name": "Soup & Stew", "slug": "soup-stew"}],
        "tags": [{"slug": "vegetarian"}, {"slug": "one-pot"}, {"slug": "comfort-food"}],
    }
    tax_sp = extract_recipe_taxonomy(dinner_soup)
    assert is_dinner_recipe(tax_sp) is True
    assert is_side_recipe(tax_sp, dinner_soup) is False

    # 2. Side dishes must NEVER be identified as dinners
    side_dish = {
        "name": "Greek Lemon Potatoes",
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tags": [{"slug": "vegan"}, {"slug": "mediterranean-greek"}, {"slug": "comfort-food"}],
    }
    tax_sd = extract_recipe_taxonomy(side_dish)
    assert is_side_recipe(tax_sd, side_dish) is True
    assert is_dinner_recipe(tax_sd) is False

    # 3. 3-bucket side classification: salad, starch, veggie
    side_candidates = [
        # Salads
        {"name": "Chimichurri Green Bean Salad", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "salad"}]},
        {"name": "Asian Slaw", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "salad"}]},
        # Starches
        {"name": "Greek Lemon Potatoes", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "vegan"}]},
        {"name": "Mexican Red Rice", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "one-pot"}]},
        # Veggies
        {"name": "Miso-Glazed Roasted Brussels Sprouts", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "skillet"}]},
        {"name": "Grilled Zucchini Ribbons", "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}], "tags": [{"slug": "grill-bbq"}]},
    ]
    for sc in side_candidates:
        sc["_taxonomy"] = extract_recipe_taxonomy(sc)

    assert classify_side_bucket(side_candidates[0], side_candidates[0]["_taxonomy"]) == "salad"
    assert classify_side_bucket(side_candidates[2], side_candidates[2]["_taxonomy"]) == "starch"
    assert classify_side_bucket(side_candidates[4], side_candidates[4]["_taxonomy"]) == "veggie"

    # Selecting 3 sides must pick 1 salad, 1 starch, 1 veggie
    trio = select_side_recipes(side_candidates, count=3)
    assert len(trio) == 3
    trio_buckets = {classify_side_bucket(s, s["_taxonomy"]) for s in trio}
    assert trio_buckets == {"salad", "starch", "veggie"}


@pytest.mark.anyio
async def test_recipes_cache_and_invalidation():
    from app.mealie_client import MealieClient

    client = MealieClient()
    client.mock_mode = True

    # 1. First fetch populates cache
    recipes1 = await client.get_all_cookbook_recipes()
    assert client._cached_all_recipes is not None
    assert len(recipes1) > 0

    # 2. Second fetch returns the same cached list
    recipes2 = await client.get_all_cookbook_recipes()
    assert recipes1 is recipes2

    # 3. Invalidate cache
    client.invalidate_recipes_cache()
    assert client._cached_all_recipes is None

    # 4. Refetch after invalidation
    recipes3 = await client.get_all_cookbook_recipes()
    assert client._cached_all_recipes is not None
    assert len(recipes3) == len(recipes1)


@pytest.mark.anyio
async def test_paginated_recipes_fetching(monkeypatch):
    from app.mealie_client import MealieClient
    import httpx

    client = MealieClient()
    client.mock_mode = False
    client.base_url = "http://fake-mealie"
    client.api_token = "fake-token"

    # Create 35 dummy recipes across 2 pages (25 on page 1, 10 on page 2)
    page1_items = [
        {"id": f"recipe-{i}", "name": f"Recipe {i}", "recipeIngredient": ["salt"]}
        for i in range(1, 26)
    ]
    page2_items = [
        {"id": f"recipe-{i}", "name": f"Recipe {i}", "recipeIngredient": ["pepper"]}
        for i in range(26, 36)
    ]

    async def mock_get(self, url, **kwargs):
        if "page=1" in url:
            return httpx.Response(200, json={"items": page1_items, "total": 35})
        elif "page=2" in url:
            return httpx.Response(200, json={"items": page2_items, "total": 35})
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    recipes = await client.get_all_cookbook_recipes(force_refresh=True)
    assert len(recipes) == 35
    assert recipes[0]["name"] == "Recipe 1"
    assert recipes[34]["name"] == "Recipe 35"
    assert client._cached_all_recipes is not None
    assert len(client._cached_all_recipes) == 35


@pytest.mark.anyio
async def test_get_dinner_options_uses_all_paginated_recipes(monkeypatch):
    from app.mealie_client import MealieClient
    import httpx

    client = MealieClient()
    client.mock_mode = False
    client.base_url = "http://fake-mealie"
    client.api_token = "fake-token"

    # 35 recipes, recipe 35 is Shepherd's Pie
    items = [
        {
            "id": f"recipe-{i}",
            "name": f"Recipe {i}",
            "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
            "recipeIngredient": ["1 lb ground beef", "2 carrots"],
            "tags": [{"slug": "beef"}],
        }
        for i in range(1, 35)
    ]
    shepherds_pie = {
        "id": "recipe-shepherds-pie",
        "name": "Classic Shepherd's Pie",
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "recipeIngredient": ["1.5 lbs ground lamb", "1 onion", "peas"],
        "tags": [{"slug": "comfort-food"}, {"slug": "lamb"}],
    }
    all_items = items + [shepherds_pie]

    async def mock_get(self, url, **kwargs):
        if "page=1" in url:
            return httpx.Response(200, json={"items": all_items[:25], "total": 35})
        elif "page=2" in url:
            return httpx.Response(200, json={"items": all_items[25:], "total": 35})
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    options = await client.get_dinner_options(count=5, mood="comfort")
    assert len(options) > 0
    # Shepherd's pie is on page 2 (item 35) and should be available in candidate pool
    all_cached_ids = [r["id"] for r in client._cached_all_recipes]
    assert "recipe-shepherds-pie" in all_cached_ids


