import pytest
from httpx import AsyncClient, ASGITransport
import tempfile
import os

from main import app
from app.pantry import (
    PantryManager,
    normalize_ingredient_name,
    categorize_ingredient,
    clean_ingredient_name,
    is_staple_ingredient,
)


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
    assert normalize_ingredient_name("4 fresh salmon fillets") == "salmon fillet"
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


def test_seed_from_foods_and_clear(temp_pantry):
    pm = temp_pantry
    foods = [
        {"name": "Organic Boneless Chicken Thighs"},
        {"name": "Fresh Asparagus"},
        {"name": "Kosher Salt"},  # Should be skipped as staple
    ]
    added = pm.seed_from_foods(foods, mark_in_stock=True)
    assert added == 2
    items = pm.get_all_items()
    assert len(items) == 2
    names = [i["name"] for i in items]
    assert "chicken thighs" in names
    assert "asparagus" in names

    # Test clear
    cleared = pm.clear_all_items()
    assert cleared == 2
    assert len(pm.get_all_items()) == 0


@pytest.mark.anyio
async def test_mealie_status_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/mealie/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "pantry" in data
        assert "total_items" in data["pantry"]


@pytest.mark.anyio
async def test_pantry_sync_with_clear_existing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Sync with clear_existing
        resp = await client.post("/api/pantry/sync?clear_existing=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "stats" in data
        assert data["stats"]["total"] > 0


def test_clean_ingredient_name_discard_junk():
    junk_inputs = [
        "Could Not Detect Ingredients",
        "**If You Like Lots Of Sauce, We Recommend Doubling The Sauce Recipe!**",
        "¹/₂ Cup",
        "****Check The Notes",
        "Other Ideas: Beans Or Lentils, Cucumbers Sliced,",
        "",
        "   ",
        "...",
        "()",
        "1/2",
        "2 Tbsp",
    ]
    for item in junk_inputs:
        assert clean_ingredient_name(item) is None, f"Expected {item!r} to be discarded"


def test_clean_ingredient_name_real_world_messy_strings():
    test_cases = [
        ("() Beef Or Chicken Broth/Stock", "beef or chicken broth stock", "Beef Or Chicken Broth/Stock"),
        ("() Boneless, Skinless Chicken Breast, Cut Into Small Pieces", "chicken breast", "Chicken Breast"),
        (". Coarsely Ground Pork", "ground pork", "Ground Pork"),
        (". Finely Ground Pork (90% Lean)", "ground pork", "Ground Pork"),
        ("/ Beef Chuck Or Brisket ((Or Gravy Or Any Other Slow Cooking Beef) Cut Into )", "beef chuck or brisket", "Beef Chuck Or Brisket"),
        ("/ Lamb Mince (Or Beef, Or 50/50 Beef/Lamb, Note 1)", "lamb mince", "Lamb Mince"),
        ("1 256 Gm Potatoes Or 4 Medium", "potato", "Potatoes"),
        ("1 290 Gm// 1 Large Or 4 Medium Onions", "onion", "Onions"),
        ("1 300 Gm/2 Large Ripe Tomatoes", "tomato", "Tomatoes"),
        ("1 6 Large Cloves Of Garlic", "garlic", "Garlic"),
        ("1 () Can Crushed Tomatoes", "tomato", "Crushed Tomatoes"),
        ("1 . Yukon Gold Potatoes, Peeled And Cut Into 1/2\" Pieces", "yukon gold potato", "Yukon Gold Potatoes"),
        ("2 X Chicken Thighs (See Notes)", "chicken thighs", "Chicken Thighs"),
        ("3 (5-Oz) Cans Tuna, Drained", "tuna", "Tuna"),
        ("1/2 Red Onion (Finely Sliced - This Is Approximately )", "red onion", "Red Onion"),
        ("2 Persian Cucumbers (Thinly Sliced)", "persian cucumber", "Persian Cucumbers"),
        ("6 Medium-Small Zucchini ( Each)", "zucchini", "Zucchini"),
        ("1 Carrot, Peeled And Shredded Or Grated", "carrot", "Carrot"),
        ("1 Large Green Cabbage, Stem/Core Removed", "green cabbage", "Green Cabbage"),
        ("1 Lime, Juiced", "lime", "Lime"),
        ("Juice From 2 Lemons", "lemon juice", "Lemon Juice"),
    ]

    for raw, expected_norm, expected_disp in test_cases:
        res = clean_ingredient_name(raw)
        assert res is not None, f"Expected clean result for {raw!r}"
        norm, disp = res
        assert norm == expected_norm, f"Norm mismatch for {raw!r}: got {norm!r}, expected {expected_norm!r}"
        assert disp == expected_disp, f"Display mismatch for {raw!r}: got {disp!r}, expected {expected_disp!r}"


def test_seed_from_recipes_deduplication_and_filtering(temp_pantry):
    pm = temp_pantry
    messy_recipes = [
        {
            "name": "Chicken Dinner 1",
            "recipeIngredient": [
                "2 X Chicken Thighs (See Notes)",
                "1 6 Large Cloves Of Garlic",
                "1 Medium Onion (Peeled And Diced)",
                "Could Not Detect Ingredients",
            ],
        },
        {
            "name": "Chicken Dinner 2",
            "recipeIngredient": [
                "5 Chicken Thighs",
                "8 Boneless, Skinless Chicken Thighs (About . Total)",
                "2 Garlic Cloves (, Finely Chopped)",
                "1 Onion Finely Chopped",
                "**If You Like Lots Of Sauce, We Recommend Doubling The Sauce Recipe!**",
            ],
        },
    ]

    added = pm.seed_from_recipes(messy_recipes, mark_in_stock=True)
    items = pm.get_all_items()
    item_names = {i["name"]: i["display_name"] for i in items}

    # Should only have 3 items: chicken thighs, garlic, onion (all duplicates merged, junk discarded)
    assert len(items) == 3
    assert "chicken thighs" in item_names
    assert item_names["chicken thighs"] == "Chicken Thighs"
    assert "garlic" in item_names
    assert item_names["garlic"] == "Garlic"
    assert "onion" in item_names
    assert item_names["onion"] == "Onion"


def test_is_staple_ingredient():
    staples = [
        "Salt & Pepper",
        "Salt And Pepper To Taste",
        "Cooking Salt / Kosher Salt",
        "Fine Sea Salt",
        "Flaky Sea Salt",
        "Kosher Salt And Freshly Ground Pepper",
        "Warm Water, Filtered",
        "Filtered Water, Room Temperature",
        "Water – Warm But Not Hot",
        "Ice Cubes",
        "Nonstick Cooking Spray, For Greasing",
        "Vegetable Spray For Greasing Bowl",
        "White Granulated Sugar",
        "& 1/2 Teaspoon Salt",
        "Water",
        "Black Pepper",
        "Kosher Salt",
        "All-Purpose Flour",
        "Sugar",
    ]
    for s in staples:
        cleaned = clean_ingredient_name(s)
        norm = cleaned[0] if cleaned else s.lower()
        assert is_staple_ingredient(norm, s), f"Expected staple for {s!r}"

    non_staples = [
        ("Chili Pepper", "chili pepper"),
        ("Bell Pepper", "bell pepper"),
        ("Brown Sugar", "brown sugar"),
        ("Coconut Sugar", "coconut sugar"),
        ("Bread Flour", "bread flour"),
        ("Watermelon", "watermelon"),
        ("Salt Pork", "salt pork"),
    ]
    for raw, expected_norm in non_staples:
        cleaned = clean_ingredient_name(raw)
        norm = cleaned[0] if cleaned else raw.lower()
        assert not is_staple_ingredient(norm, raw), f"Expected NOT staple for {raw!r}"


def test_clean_ingredient_units_ordinals_and_junk():
    test_cases = [
        # Standalone units without numbers
        ("Lb Ground Pork", "ground pork", "Ground Pork"),
        ("Lb Lamb Mince", "lamb mince", "Lamb Mince"),
        ("Lbs 16-20 Black Tiger Shrimp", "black tiger shrimp", "Black Tiger Shrimp"),
        ("Oz Chicken Breast", "chicken breast", "Chicken Breast"),
        ("Pound Boneless, Skinless Chicken Thighs", "chicken thighs", "Chicken Thighs"),
        ("Pound Ground Chicken", "ground chicken", "Ground Chicken"),
        ("Pounds Boneless, Skinless Chicken Breast", "chicken breast", "Chicken Breast"),
        ("Lb. Carrots", "carrot", "Carrots"),
        ("Pound Potatoes", "potato", "Potatoes"),
        ("Oz Carrot", "carrot", "Carrot"),
        ("Oz / 400G Can Crushed Tomatoes", "tomato", "Crushed Tomatoes"),
        ("Oz/ 1 Large Or 4 Medium Onions", "onion", "Onions"),
        ("Stick Butter, Melted", "butter", "Butter"),
        ("Bunch Mint", "mint", "Mint"),
        ("Bunch Scallions", "scallion", "Scallions"),
        ("Quarts Vegetable Oil", "vegetable oil", "Vegetable Oil"),
        ("Ounce Can Black Beans", "black bean", "Black Beans"),
        ("Inch Fresh Ginger", "ginger", "Ginger"),
        ("Tiny Pinch Garlic Powder", "garlic powder", "Garlic Powder"),
        # Ordinals & fractions
        ("Th Cup Heavy Cream", "heavy cream", "Heavy Cream"),
        ("Th Cup Plain Unflavored Yogurt", "plain unflavored yogurt", "Plain Unflavored Yogurt"),
        ("Rd Cup Frozen/Fresh Green Peas", "frozen green pea", "Frozen/Fresh Green Peas"),
        ("Th Teaspoon Ground Mace Or Nutmeg", "ground mace or nutmeg", "Ground Mace Or Nutmeg"),
        # Connectors & symbols
        ("& 1/2 Inch Cinnamon Stick", "cinnamon stick", "Cinnamon Stick"),
        ("And 1/2 Cups Graham Cracker Crumbs", "graham cracker crumb", "Graham Cracker Crumbs"),
        ("Plus 2 Tablespoons Olive Oil", "olive oil", "Olive Oil"),
        ("T Rice Vinegar", "rice vinegar", "Rice Vinegar"),
        ("T Sriracha Sauce", "sriracha sauce", "Sriracha Sauce"),
        ("Sharp White Cheddar |", "sharp white cheddar", "Sharp White Cheddar"),
        # Prefixes & mangling
        ("-Squeezed Lime Juice", "lime juice", "Lime Juice"),
        ("Fresh-Squeezed Lime Juice", "lime juice", "Lime Juice"),
        ("Ly Chopped Parsley Or Chives For Garnish", "parsley or chives", "Parsley Or Chives"),
        ("Freshly Chopped Parsley Or Chives For Garnish", "parsley or chives", "Parsley Or Chives"),
    ]

    for raw, exp_norm, exp_disp in test_cases:
        res = clean_ingredient_name(raw)
        assert res is not None, f"Expected clean result for {raw!r}"
        norm, disp = res
        assert norm == exp_norm, f"Norm mismatch for {raw!r}: got {norm!r}, expected {exp_norm!r}"
        assert disp == exp_disp, f"Display mismatch for {raw!r}: got {disp!r}, expected {exp_disp!r}"

    # Instructional / serving junk discarded
    discard_cases = [
        "For Greasing The Skillet",
        "Recipe Guacamole, For Serving, If Desired",
        "Vegetables Of Choice",
        "Skewers",
        "Pound Peeled, I Use 31-40 Count Size",
    ]
    for junk in discard_cases:
        res = clean_ingredient_name(junk)
        assert res is None, f"Expected {junk!r} to be discarded, got {res!r}"


def test_categorization_improvements():
    checks = [
        ("Graham Cracker Crumbs", "grains & bakery"),
        ("Ham", "protein"),
        ("Pound Breakfast Sausage", "protein"),
        ("Eggs", "dairy"),
        ("Eggplant", "produce"),
        ("Peppercorns", "spices & herbs"),
        ("Sweet Corn", "produce"),
        ("Green Peas", "produce"),
        ("Bunch Scallions", "produce"),
        ("Bunch Mint", "produce"),
        ("Celery", "produce"),
        ("Mushrooms", "produce"),
    ]
    for item, expected in checks:
        cat = categorize_ingredient(item)
        assert cat == expected, f"{item}: got {cat}, expected {expected}"


def test_cleanup_existing_items_in_place_migration(tmp_path):
    db_file = tmp_path / "migration_pantry.db"
    pm = PantryManager(db_path=str(db_file))

    # Insert messy rows directly
    with pm._get_connection() as conn:
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("lb ground pork", "Lb Ground Pork", "protein", 1),
        )
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("pound ground chicken", "Pound Ground Chicken", "protein", 1),
        )
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("salt and pepper", "Salt & Pepper", "pantry", 1),
        )
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("for greasing the skillet", "For Greasing The Skillet", "pantry", 1),
        )
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("bunch scallions", "Bunch Scallions", "grains & bakery", 1),
        )
        conn.execute(
            "INSERT INTO pantry_items (name, display_name, category, in_stock) VALUES (?, ?, ?, ?)",
            ("sharp white cheddar |", "Sharp White Cheddar |", "dairy", 1),
        )
        conn.commit()

    # Run in-place cleanup
    cleaned = pm.cleanup_existing_items()
    assert cleaned >= 6

    items = pm.get_all_items()
    item_map = {i["name"]: i for i in items}

    # Staples and junk should be removed
    assert "salt and pepper" not in item_map
    assert "for greasing the skillet" not in item_map

    # Messy items should be migrated to clean names & categories
    assert "ground pork" in item_map
    assert item_map["ground pork"]["display_name"] == "Ground Pork"
    assert item_map["ground pork"]["category"] == "protein"

    assert "ground chicken" in item_map
    assert item_map["ground chicken"]["display_name"] == "Ground Chicken"
    assert item_map["ground chicken"]["category"] == "protein"

    assert "scallion" in item_map
    assert item_map["scallion"]["display_name"] == "Scallions"
    assert item_map["scallion"]["category"] == "produce"

    assert "sharp white cheddar" in item_map
    assert item_map["sharp white cheddar"]["display_name"] == "Sharp White Cheddar"
    assert item_map["sharp white cheddar"]["category"] == "dairy"


