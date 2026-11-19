import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from app.mealie_client import MealieClient
from app.mock_data import MOCK_RECIPES, MOCK_SIDES


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_search_empty_and_whitespace_query():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for q in ("", "   "):
            resp = await client.get("/api/recipes/search", params={"q": q})
            assert resp.status_code == 200
            data = resp.json()
            assert data["results"] == []
            assert data["count"] == 0
            assert data["query"] == ""


@pytest.mark.anyio
async def test_search_by_name_returns_enriched_results():
    target_recipe = MOCK_RECIPES[0]
    first_word = target_recipe["name"].split()[0]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/recipes/search", params={"q": target_recipe["name"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        top = data["results"][0]
        assert top["id"] == target_recipe["id"]
        assert top["name"] == target_recipe["name"]
        assert top["imageUrl"] == f"/api/recipe-image/{target_recipe['id']}"
        assert "totalTime" in top
        assert "pantry" in top
        assert isinstance(top["badges"], list)
        assert top["match_field"] == "name"

        # Case-insensitive partial query
        resp_partial = await client.get("/api/recipes/search", params={"q": first_word.lower()})
        assert resp_partial.status_code == 200
        ids = [r["id"] for r in resp_partial.json()["results"]]
        assert target_recipe["id"] in ids


@pytest.mark.anyio
async def test_search_no_matches_returns_empty_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/recipes/search", params={"q": "zzznonexistentrecipe12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["count"] == 0


@pytest.mark.anyio
async def test_search_limit_and_clamping():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/recipes/search", params={"q": "a", "limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) <= 2
        assert data["count"] == len(data["results"])


@pytest.mark.anyio
async def test_search_ranking_name_ingredient_and_scope():
    """Unit test relevance ranking across title, ingredient, and main/side scope boosts."""
    client = MealieClient()
    client.mock_mode = True
    sample_recipes = [
        {
            "id": "r-main-garlic",
            "name": "Garlic Herb Chicken",
            "slug": "garlic-herb-chicken",
            "description": "Juicy roasted chicken",
            "totalTime": "35 mins",
            "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
            "tags": [{"name": "chicken", "slug": "chicken"}],
            "recipeIngredient": [
                {"food": {"name": "Chicken Breast"}, "display": "2 chicken breasts"},
                {"food": {"name": "Garlic"}, "display": "4 cloves garlic"},
            ],
        },
        {
            "id": "r-side-garlic",
            "name": "Garlic Roasted Broccolini",
            "slug": "garlic-roasted-broccolini",
            "description": "Crisp tender side dish",
            "totalTime": "15 mins",
            "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
            "tags": [{"name": "side", "slug": "side"}],
            "recipeIngredient": [
                {"food": {"name": "Broccolini"}, "display": "1 bunch broccolini"},
                {"food": {"name": "Garlic"}, "display": "2 cloves garlic"},
            ],
        },
        {
            "id": "r-ing-only",
            "name": "Weeknight Skillet Bowl",
            "slug": "weeknight-skillet-bowl",
            "description": "Quick savory bowl",
            "totalTime": "20 mins",
            "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
            "tags": [{"name": "skillet", "slug": "skillet"}],
            "recipeIngredient": [
                {"food": {"name": "Saffron"}, "display": "1 pinch saffron"},
                {"food": {"name": "Garlic"}, "display": "3 cloves garlic"},
            ],
        },
    ]

    async def fake_all(force_refresh: bool = False):
        return sample_recipes

    client.get_all_cookbook_recipes = fake_all  # type: ignore[method-assign]

    # Scope=main ranks main dinner title above side dish title, and title above ingredient-only match
    main_res = await client.search_recipes("garlic", scope="main")
    assert [r["id"] for r in main_res] == ["r-main-garlic", "r-side-garlic", "r-ing-only"]
    assert main_res[0]["match_field"] == "name"
    assert main_res[2]["match_field"] == "ingredient"

    # Scope=side boosts side dish above main dinner
    side_res = await client.search_recipes("garlic", scope="side")
    assert side_res[0]["id"] == "r-side-garlic"
    assert side_res[0]["is_side"] is True

    # Ingredient-only query finds the recipe and marks match_field as ingredient
    ing_res = await client.search_recipes("saffron", scope="main")
    assert len(ing_res) == 1
    assert ing_res[0]["id"] == "r-ing-only"
    assert ing_res[0]["match_field"] == "ingredient"

    # Multi-word query narrows down accurately across fields
    multi_res = await client.search_recipes("saffron skillet", scope="main")
    assert [r["id"] for r in multi_res] == ["r-ing-only"]


@pytest.mark.anyio
async def test_choose_searched_recipe_and_side_submits_mealie_ids():
    """Selecting a Mealie recipe from search submits recipe_id / side_recipe_id (not custom_note)."""
    main_recipe = MOCK_RECIPES[0]
    side_recipe = MOCK_SIDES[0]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/choose",
            json={
                "recipe_id": main_recipe["id"],
                "side_recipe_id": side_recipe["id"],
                "target_date": "2026-12-20",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_custom"] is False
        assert data["dish_name"] == main_recipe["name"]
        assert data["side_name"] == side_recipe["name"]

        # Clean up mock plan
        await client.post("/api/plan/reset", json={"target_date": "2026-12-20"})


def test_frontend_has_amalgamated_search_hooks():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    for marker in (
        "/api/recipes/search",
        "mealieSearchResults",
        "selectedSearchRecipeCard",
        "sideMealieSearchResults",
        "selectedSearchSideCard",
        "selectSearchedRecipe",
        "selectSearchedSide",
        "handleCustomKeydown",
        "handleCustomSideKeydown",
        "mobileSearchSpacer",
        "scrollSearchCardIntoView",
        "updateMobileSearchSpacer",
        "renderSearchLoadingState",
        "handleSearchInputBlur",
        "search-scroll-list",
        "visualViewport",
    ):
        assert marker in html, f"Expected amalgamated search marker '{marker}' in static/index.html"
