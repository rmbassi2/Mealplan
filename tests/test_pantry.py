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
    get_ingredient_tier,
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
        assert "tiers" in data
        assert "tier_stats" in data
        assert "anchors" in data["tiers"]
        assert "perishables" in data["tiers"]
        assert "staples" in data["tiers"]
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

        # 5. Bulk stock endpoints (body and query param)
        bulk_resp1 = await client.post("/api/pantry/bulk-stock", json={"in_stock": True})
        assert bulk_resp1.status_code == 200
        assert bulk_resp1.json()["status"] == "success"

        bulk_resp2 = await client.post("/api/pantry/bulk-stock?in_stock=true")
        assert bulk_resp2.status_code == 200
        assert bulk_resp2.json()["status"] == "success"


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
            # Every option in pantry mood must be ready (status ready or almost_ready with missing_perishables <= 2)
            assert opt["pantry"]["is_ready"] is True
            assert opt["pantry"]["status"] in ("ready", "almost_ready")
            assert opt["pantry"]["missing_count"] <= 2
            # Check badge present
            badges = [b["label"] for b in opt["badges"]]
            assert any("Ready" in b or "Pantry" in b or "Need:" in b for b in badges)


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
        ("() Beef Or Chicken Broth/Stock", "beef broth", "Beef Broth"),
        ("() Boneless, Skinless Chicken Breast, Cut Into Small Pieces", "chicken breast", "Chicken Breast"),
        (". Coarsely Ground Pork", "ground pork", "Ground Pork"),
        (". Finely Ground Pork (90% Lean)", "ground pork", "Ground Pork"),
        ("/ Beef Chuck Or Brisket ((Or Gravy Or Any Other Slow Cooking Beef) Cut Into )", "beef chuck roast", "Beef Chuck Roast"),
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
        ("2 Persian Cucumbers (Thinly Sliced)", "cucumber", "Cucumbers"),
        ("6 Medium-Small Zucchini ( Each)", "zucchini", "Zucchini"),
        ("1 Carrot, Peeled And Shredded Or Grated", "carrot", "Carrot"),
        ("1 Large Green Cabbage, Stem/Core Removed", "cabbage", "Cabbage"),
        ("1 Lime, Juiced", "lime", "Lime"),
        ("Juice From 2 Lemons", "lemon", "Lemon"),
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
        ("Lbs 16-20 Black Tiger Shrimp", "shrimp", "Shrimp"),
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
        ("Th Cup Plain Unflavored Yogurt", "plain yogurt", "Plain Yogurt"),
        ("Rd Cup Frozen/Fresh Green Peas", "pea", "Peas (Frozen)"),
        ("Th Teaspoon Ground Mace Or Nutmeg", "nutmeg", "Nutmeg"),
        # Connectors & symbols
        ("& 1/2 Inch Cinnamon Stick", "cinnamon stick", "Cinnamon Stick"),
        ("And 1/2 Cups Graham Cracker Crumbs", "graham cracker crumb", "Graham Cracker Crumbs"),
        ("Plus 2 Tablespoons Olive Oil", "olive oil", "Olive Oil"),
        ("T Rice Vinegar", "rice vinegar", "Rice Vinegar"),
        ("T Sriracha Sauce", "sriracha", "Sriracha"),
        ("Sharp White Cheddar |", "cheddar", "Cheddar"),
        # Prefixes & mangling
        ("-Squeezed Lime Juice", "lime", "Lime"),
        ("Fresh-Squeezed Lime Juice", "lime", "Lime"),
        ("Ly Chopped Parsley Or Chives For Garnish", "parsley", "Parsley"),
        ("Freshly Chopped Parsley Or Chives For Garnish", "parsley", "Parsley"),
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
        "Length Ginger",
        "To 15 Green Beans",
        "Pecans Or Walnuts",
        "Cheese",
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

    assert "cheddar" in item_map
    assert item_map["cheddar"]["display_name"] == "Cheddar"
    assert item_map["cheddar"]["category"] == "dairy"


def test_pantry_refinements_and_misplacements():
    # 1. Measurement strings & scrape glitches (deleted immediately)
    assert clean_ingredient_name("To 2 Scotch Bonnet Peppers Or Habanero Chiles") is None
    assert clean_ingredient_name("Ginger Chili Garlic") is None
    assert clean_ingredient_name("Pickled Jalapeno Juice") is None
    assert clean_ingredient_name("Broth") is None
    assert clean_ingredient_name("Stock") is None
    assert clean_ingredient_name("Length Ginger") is None
    assert clean_ingredient_name("To 15 Green Beans") is None
    assert clean_ingredient_name("Skewers") is None
    assert clean_ingredient_name("Vegetables Of Choice") is None
    assert clean_ingredient_name("Cheese") is None

    # 2. Derivative ingredients (consolidated into root parent item)
    assert clean_ingredient_name("Lemon Juice") == ("lemon", "Lemon")
    assert clean_ingredient_name("Lemon Zest") == ("lemon", "Lemon")
    assert clean_ingredient_name("Lime Juice") == ("lime", "Lime")
    assert clean_ingredient_name("Lime Zest") == ("lime", "Lime")
    assert clean_ingredient_name("Egg Yolk") == ("egg", "Eggs")
    assert clean_ingredient_name("Egg Whites") == ("egg", "Eggs")
    assert clean_ingredient_name("Levain") == ("sourdough starter", "Sourdough Starter")
    assert clean_ingredient_name("Sourdough Discard") == ("sourdough starter", "Sourdough Starter")

    # 3. Category deduplications and overlaps
    assert clean_ingredient_name("Chocolate Chips") == ("chocolate chip", "Chocolate Chips")
    assert clean_ingredient_name("Chocolate Chip") == ("chocolate chip", "Chocolate Chips")
    assert clean_ingredient_name("Dark Chocolate Chips") == ("chocolate chip", "Chocolate Chips")
    assert clean_ingredient_name("Semisweet Chocolate Chips") == ("chocolate chip", "Chocolate Chips")
    assert clean_ingredient_name("Black Beans") == ("black bean", "Black Beans")
    assert clean_ingredient_name("Canned Black Beans") == ("black bean", "Black Beans")
    assert clean_ingredient_name("Almonds") == ("almond", "Almonds")
    assert clean_ingredient_name("Raw Almonds") == ("almond", "Almonds")
    assert clean_ingredient_name("Slivered Almonds") == ("almond", "Almonds")
    assert clean_ingredient_name("Pecans Or Walnuts") is None
    assert clean_ingredient_name("Walnuts") == ("walnut", "Walnuts")
    assert clean_ingredient_name("Chardonnay") == ("white wine", "White Wine")
    assert clean_ingredient_name("Wine") == ("white wine", "White Wine")

    # Produce
    assert clean_ingredient_name("Peas") == ("pea", "Peas (Frozen)")
    assert clean_ingredient_name("Frozen Peas") == ("pea", "Peas (Frozen)")
    assert clean_ingredient_name("Cilantro") == ("cilantro", "Cilantro")
    assert clean_ingredient_name("Coriander Leaves") == ("cilantro", "Cilantro")
    assert clean_ingredient_name("Green Cabbage") == ("cabbage", "Cabbage")
    assert clean_ingredient_name("Persian Cucumbers") == ("cucumber", "Cucumbers")
    assert clean_ingredient_name("Green Chile Peppers") == ("green chile", "Green Chiles")
    assert clean_ingredient_name("Firm Tofu") == ("tofu", "Tofu")

    # Grains & Bakery
    assert clean_ingredient_name("Breadcrumbs") == ("breadcrumb", "Breadcrumbs")
    assert clean_ingredient_name("Regular Breadcrumbs") == ("breadcrumb", "Breadcrumbs")
    assert clean_ingredient_name("Panko Breadcrumbs") == ("panko", "Panko")
    assert clean_ingredient_name("Rice") == ("white rice", "White Rice")
    assert clean_ingredient_name("Chang'S Pad Thai Dried Rice Sticks") == ("rice noodle", "Rice Noodles")
    assert clean_ingredient_name("Rice Noodles") == ("rice noodle", "Rice Noodles")

    # Spices
    assert clean_ingredient_name("Chili Flakes") == ("chili flake", "Chili Flakes / Red Pepper Flakes")
    assert clean_ingredient_name("Red Pepper Flakes") == ("chili flake", "Chili Flakes / Red Pepper Flakes")

    # 4. Categorization routing
    assert categorize_ingredient("Green Beans") == "produce"
    assert categorize_ingredient("Red Wine Vinegar") == "sauces & condiments"
    assert categorize_ingredient("Seasoned Rice Wine Vinegar") == "sauces & condiments"
    assert categorize_ingredient("White Wine Vinegar") == "sauces & condiments"
    assert categorize_ingredient("Chili Crisp") == "sauces & condiments"
    assert categorize_ingredient("Thai Red Curry Paste") == "sauces & condiments"
    assert categorize_ingredient("Ground Ginger") == "spices & herbs"
    assert categorize_ingredient("Baking Soda") == "spices & herbs"
    assert categorize_ingredient("Ground Cloves") == "spices & herbs"
    assert categorize_ingredient("Whole Cloves") == "spices & herbs"
    assert categorize_ingredient("Cream Of Chicken") == "pantry"


def test_always_on_staples_vs_active_stock(temp_pantry):
    pm = temp_pantry

    recipe = {
        "name": "Chicken Cumin Stir Fry",
        "recipeIngredient": [
            "1 Lb Chicken Thighs",
            "1 Tsp Ground Cumin",
            "1 Tbsp Soy Sauce",
            "1/2 Tsp Black Pepper",
            "1 Tsp Cornstarch",
            "1 Tbsp Olive Oil",
            "1 Fresh Avocado",
        ],
    }

    # Empty active stock: only Active Stock perishables (Chicken Thighs, Avocado) are missing
    result = pm.evaluate_recipe(recipe, in_stock_set=set())
    assert "Chicken Thighs" in result["missing_items"]
    assert "Avocado" in result["missing_items"]
    assert "Ground Cumin" not in result["missing_items"]
    assert "Soy Sauce" not in result["missing_items"]
    assert "Black Pepper" not in result["missing_items"]
    assert "Cornstarch" not in result["missing_items"]
    assert "Olive Oil" not in result["missing_items"]
    assert result["missing_count"] == 2
    assert not result["is_ready"]

    # With Active Stock on hand, recipe is ready and full pantry
    active_stock = {"chicken thighs", "avocado"}
    result_ready = pm.evaluate_recipe(recipe, in_stock_set=active_stock)
    assert result_ready["missing_count"] == 0
    assert result_ready["is_ready"]
    assert result_ready["is_full_pantry"]


def test_tiered_classification():
    """Verify ingredients are categorized into the three Dinner Availability tiers correctly."""
    # Tier 1: Anchors
    assert get_ingredient_tier("chicken breast") == "anchor"
    assert get_ingredient_tier("beef chuck roast") == "anchor"
    assert get_ingredient_tier("ground pork") == "anchor"
    assert get_ingredient_tier("salmon fillet") == "anchor"
    assert get_ingredient_tier("cod fillets") == "anchor"
    assert get_ingredient_tier("black tiger shrimp") == "anchor"
    assert get_ingredient_tier("extra-firm tofu") == "anchor"
    assert get_ingredient_tier("italian sausage") == "anchor"

    # Excluded from anchors -> staple
    assert get_ingredient_tier("bacon fat") == "staple"
    assert get_ingredient_tier("chicken broth") == "staple"
    assert get_ingredient_tier("beef stock") == "staple"
    assert get_ingredient_tier("fish sauce") == "staple"

    # Tier 2: Perishables
    assert get_ingredient_tier("baby spinach") == "perishable"
    assert get_ingredient_tier("cilantro") == "perishable"
    assert get_ingredient_tier("heavy cream") == "perishable"
    assert get_ingredient_tier("sour cream") == "perishable"
    assert get_ingredient_tier("avocado") == "perishable"
    assert get_ingredient_tier("garlic") == "perishable"
    assert get_ingredient_tier("fresh ginger") == "perishable"
    assert get_ingredient_tier("fresh lime") == "perishable"
    assert get_ingredient_tier("scallions") == "perishable"
    assert get_ingredient_tier("mozzarella") == "perishable"

    # Tier 3: Staples
    assert get_ingredient_tier("garlic powder") == "staple"
    assert get_ingredient_tier("onion powder") == "staple"
    assert get_ingredient_tier("ground ginger") == "staple"
    assert get_ingredient_tier("canned black beans") == "staple"
    assert get_ingredient_tier("tomato paste") == "staple"
    assert get_ingredient_tier("olive oil") == "staple"
    assert get_ingredient_tier("smoked paprika") == "staple"
    assert get_ingredient_tier("all purpose flour") == "staple"
    assert get_ingredient_tier("white rice") == "staple"
    assert get_ingredient_tier("butter") == "staple"


def test_tiered_dinner_availability_evaluation(temp_pantry):
    """Test weighted Dinner Availability states: ready, almost_ready, unavailable."""
    pm = temp_pantry

    recipe = {
        "name": "Chicken Tikka Skillet",
        "recipeIngredient": [
            "1.5 lbs Boneless Chicken Thighs",  # Anchor
            "1 cup Heavy Cream",                # Perishable 1
            "1/4 cup Chopped Cilantro",         # Perishable 2
            "1 Fresh Lime",                     # Perishable 3
            "2 tbsp Olive Oil",                 # Staple
            "1 tsp Cumin",                      # Staple
            "1 tsp Garam Masala",               # Staple
            "1 tsp Salt",                       # Staple
        ],
    }

    # 1. Anchor missing -> Unavailable (Hard Blocker) even if perishables are present
    stock_no_protein = {"heavy cream", "cilantro", "lime"}
    res_no_protein = pm.evaluate_recipe(recipe, in_stock_set=stock_no_protein)
    assert res_no_protein["status"] == "unavailable"
    assert not res_no_protein["is_ready"]
    assert not res_no_protein["anchor_satisfied"]
    assert "Chicken Thighs" in res_no_protein["missing_anchor"]

    # 2. Anchor in stock + 0 missing perishables -> Ready to Cook
    stock_all_fresh = {"chicken thighs", "heavy cream", "cilantro", "lime"}
    res_ready = pm.evaluate_recipe(recipe, in_stock_set=stock_all_fresh)
    assert res_ready["status"] == "ready"
    assert res_ready["is_ready"]
    assert res_ready["is_full_pantry"]
    assert res_ready["missing_count"] == 0

    # 3. Anchor in stock + 1 missing perishable -> Almost Ready
    stock_missing_one = {"chicken thighs", "heavy cream", "cilantro"}
    res_one_off = pm.evaluate_recipe(recipe, in_stock_set=stock_missing_one)
    assert res_one_off["status"] == "almost_ready"
    assert res_one_off["is_ready"]
    assert not res_one_off["is_full_pantry"]
    assert len(res_one_off["missing_perishables"]) == 1
    assert "Lime" in res_one_off["missing_perishables"][0]

    # 4. Anchor in stock + 2 missing perishables -> Almost Ready (Soft Tolerance)
    stock_missing_two = {"chicken thighs", "heavy cream"}
    res_two_off = pm.evaluate_recipe(recipe, in_stock_set=stock_missing_two)
    assert res_two_off["status"] == "almost_ready"
    assert res_two_off["is_ready"]
    assert len(res_two_off["missing_perishables"]) == 2

    # 5. Anchor in stock + 3 missing perishables -> Unavailable (> 2 fresh missing)
    stock_missing_three = {"chicken thighs"}
    res_three_off = pm.evaluate_recipe(recipe, in_stock_set=stock_missing_three)
    assert res_three_off["status"] == "unavailable"
    assert not res_three_off["is_ready"]
    assert len(res_three_off["missing_perishables"]) == 3


def test_get_tiered_dashboard(temp_pantry):
    """Verify get_tiered_dashboard returns items cleanly separated into 3 tiers."""
    pm = temp_pantry
    pm.upsert_item("chicken breast", in_stock=True)
    pm.upsert_item("baby spinach", in_stock=False)
    pm.upsert_item("olive oil", in_stock=True)

    dashboard = pm.get_tiered_dashboard()
    assert "anchors" in dashboard
    assert "perishables" in dashboard
    assert "staples" in dashboard
    assert len(dashboard["anchors"]) == 1
    assert dashboard["anchors"][0]["name"] == "chicken breast"
    assert len(dashboard["perishables"]) == 1
    assert dashboard["perishables"][0]["name"] == "baby spinach"
    assert len(dashboard["staples"]) == 1
    assert dashboard["staples"][0]["name"] == "olive oil"

    assert dashboard["tier_stats"]["anchors_total"] == 1
    assert dashboard["tier_stats"]["anchors_in_stock"] == 1
    assert dashboard["tier_stats"]["perishables_total"] == 1
    assert dashboard["tier_stats"]["perishables_in_stock"] == 0
    assert dashboard["tier_stats"]["staples_total"] == 1


def test_pantry_badges_consistency_and_dict_category_handling():
    """Verify that extract_recipe_taxonomy never produces negative pantry badges like 'No Chicken Breast'
    and that is_dinner_recipe/is_side_recipe safely handle dict category representations without throwing.
    """
    from app.taxonomy import extract_recipe_taxonomy, is_dinner_recipe, is_side_recipe

    # 1. Recipe with _pantry metadata attached
    recipe = {
        "name": "Homemade Earls Cajun Chicken",
        "description": "Blackened chicken breast with garlic butter",
        "recipeIngredient": ["chicken breasts", "black peppercorns", "butter"],
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "categories": [{"name": "Dinner", "slug": "dinner"}],
        "_pantry": {
            "status": "ready",
            "is_ready": True,
            "anchor_protein": "Chicken Breast",
            "missing_anchor": None,
            "missing_count": 0,
            "missing_items": [],
        },
    }

    tax = extract_recipe_taxonomy(recipe)
    badge_labels = [b["label"] for b in tax["badges"]]
    # Taxonomy badges should NEVER contain negative missing anchor labels like "No Chicken Breast"
    assert not any("No " in b for b in badge_labels)
    assert not any(b.get("type") == "pantry" for b in tax["badges"])

    # 2. Even if evaluated as unavailable with missing_anchor, static taxonomy badges must remain clean
    recipe_unavailable = dict(recipe)
    recipe_unavailable["_pantry"] = {
        "status": "unavailable",
        "is_ready": False,
        "anchor_protein": "Chicken Breast",
        "missing_anchor": "Chicken Breast",
        "missing_count": 1,
        "missing_items": ["Chicken Breast"],
    }
    tax_unavail = extract_recipe_taxonomy(recipe_unavailable)
    unavail_badge_labels = [b["label"] for b in tax_unavail["badges"]]
    assert not any("No " in b for b in unavail_badge_labels)
    assert not any("Missing" in b for b in unavail_badge_labels)

    # 3. is_dinner_recipe and is_side_recipe must safely parse raw Mealie dict categories
    assert is_dinner_recipe(recipe) is True
    assert is_side_recipe(recipe) is False





