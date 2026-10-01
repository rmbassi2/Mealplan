import pytest
from httpx import AsyncClient, ASGITransport
import tempfile
import os

from main import app
from app.pantry import PantryManager, normalize_ingredient_name, categorize_ingredient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def temp_pantry(tmp_path):
    db_file = tmp_path / "test_pantry.db"
    pm = PantryManager(db_path=str(db_file))
    return pm


def test_ingredient_normalization():
    assert normalize_ingredient_name("2 cups boneless skinless chicken breast") == "chicken breast"
    assert normalize_ingredient_name("1/2 tsp kosher salt") == "kosher salt"
    assert normalize_ingredient_name("4 fresh salmon fillets") == "salmon fillets"
    assert normalize_ingredient_name("1 can (8 oz) tomato sauce") == "tomato sauce"
    assert normalize_ingredient_name("3 cloves minced garlic") == "garlic"


def test_categorization():
    assert categorize_ingredient("chicken breast") == "protein"
    assert categorize_ingredient("heavy cream") == "dairy"
    assert categorize_ingredient("baby spinach") == "produce"
    assert categorize_ingredient("arborio rice") == "grains & bakery"
    assert categorize_ingredient("soy sauce") == "sauces & condiments"
    assert categorize_ingredient("smoked paprika") == "spices & herbs"


def test_pantry_manager_crud_and_evaluation(temp_pantry):
    pm = temp_pantry

    # Initial stats should be empty
    stats = pm.get_stats()
    assert stats["total"] == 0

    # Add items
    pm.upsert_item("chicken breast", display_name="Chicken Breast", in_stock=True)
    pm.upsert_item("heavy cream", display_name="Heavy Cream", in_stock=True)
    pm.upsert_item("baby spinach", display_name="Baby Spinach", in_stock=False)

    stats = pm.get_stats()
    assert stats["total"] == 3
    assert stats["in_stock"] == 2
    assert stats["out_of_stock"] == 1

    # In-stock set contains chicken and cream, plus default staples
    in_stock = pm.get_in_stock_set()
    assert "chicken breast" in in_stock
    assert "heavy cream" in in_stock
    assert "baby spinach" not in in_stock
    assert "salt" in in_stock  # Built-in staple

    # Toggle baby spinach to in_stock
    updated = pm.toggle_item(name="baby spinach", in_stock=True)
    assert updated["in_stock"] == 1
    assert "baby spinach" in pm.get_in_stock_set()

    # Toggle back to out_of_stock
    pm.toggle_item(name="baby spinach", in_stock=False)
    assert "baby spinach" not in pm.get_in_stock_set()

    # Evaluate recipe with 1 missing item (spinach)
    sample_recipe = {
        "name": "Tuscan Chicken",
        "recipeIngredient": [
            {"food": {"name": "Chicken Breast"}, "display": "2 chicken breasts"},
            {"food": {"name": "Heavy Cream"}, "display": "1 cup heavy cream"},
            {"food": {"name": "Baby Spinach"}, "display": "2 cups baby spinach"},
            {"food": {"name": "Kosher Salt"}, "display": "1 tsp salt"},  # Staple
        ],
    }

    eval_result = pm.evaluate_recipe(sample_recipe)
    assert eval_result["missing_count"] == 1
    assert "Baby Spinach" in eval_result["missing_items"][0]
    assert eval_result["is_ready"] is True
    assert eval_result["is_full_pantry"] is False

    # Mark spinach in-stock -> recipe becomes 100% ready
    pm.toggle_item(name="baby spinach", in_stock=True)
    eval_full = pm.evaluate_recipe(sample_recipe)
    assert eval_full["missing_count"] == 0
    assert eval_full["is_ready"] is True
    assert eval_full["is_full_pantry"] is True


@pytest.mark.anyio
async def test_api_pantry_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Get pantry
        resp = await client.get("/api/pantry")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "stats" in data
        assert data["stats"]["total"] > 0

        # Pick first item to toggle
        first_item = data["items"][0]
        initial_status = first_item["in_stock"]

        # 2. Toggle item
        toggle_resp = await client.post(
            "/api/pantry/toggle",
            json={"item_id": first_item["id"], "in_stock": not initial_status},
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["item"]["in_stock"] == (0 if initial_status == 1 else 1)

        # Toggle back
        await client.post(
            "/api/pantry/toggle",
            json={"item_id": first_item["id"], "in_stock": bool(initial_status)},
        )

        # 3. Add custom item
        add_resp = await client.post(
            "/api/pantry/item",
            json={
                "name": "test saffron threads",
                "display_name": "Saffron Threads",
                "category": "spices & herbs",
                "in_stock": True,
            },
        )
        assert add_resp.status_code == 200
        new_item = add_resp.json()["item"]
        assert new_item["name"] == "test saffron threads"

        # 4. Delete item
        del_resp = await client.delete(f"/api/pantry/item/{new_item['id']}")
        assert del_resp.status_code == 200


@pytest.mark.anyio
async def test_options_with_pantry_filter():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Query options with pantry mood
        resp = await client.get("/api/options?mood=pantry")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["options"]) > 0

        for opt in data["options"]:
            assert "pantry" in opt
            # Every option in pantry mood must be ready (missing_count <= 1)
            assert opt["pantry"]["is_ready"] is True
            assert opt["pantry"]["missing_count"] <= 1
            # Check badge present
            badges = [b["label"] for b in opt["badges"]]
            assert any("Pantry" in b or "Need:" in b for b in badges)


@pytest.mark.anyio
async def test_shopping_list_add_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/shopping-list/add",
            json={
                "item_name": "Heavy Cream",
                "recipe_id": "test-recipe-123",
                "note": "1 ingredient off from Tuscan Chicken",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Heavy Cream" in data["item_name"]
