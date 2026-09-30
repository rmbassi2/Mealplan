"""Taxonomy definitions, classification, and smart selection logic for Mealie recipes."""

import random
from datetime import date
from typing import Any, Dict, List, Optional, Set

# User's exact taxonomy schema
TAXONOMY = {
    "categories": [
        "Dinner",
        "Lunch",
        "Breakfast",
        "Side Dish",
        "Soup & Stew",
        "Dessert & Sweets",
        "Baking & Bread",
        "Appetizer & Snack",
        "Sauces & Condiments",
        "Beverages",
    ],
    "tools": [
        "Slow Cooker",
        "Instant Pot",
        "Air Fryer",
        "Cast Iron Skillet",
        "Dutch Oven",
        "Sheet Pan",
        "Grill",
        "Blender",
        "Food Processor",
        "Wok",
        "Baking Dish",
    ],
    "tag_dimensions": {
        "protein": [
            "chicken",
            "beef",
            "pork",
            "seafood",
            "turkey",
            "lamb",
            "vegetarian",
            "vegan",
            "tofu-tempeh",
            "beans-legumes",
            "pasta-noodles",
            "egg",
        ],
        "cooking_style": [
            "one-pot",
            "sheet-pan",
            "skillet",
            "baked-casserole",
            "grill-bbq",
            "no-cook",
            "stir-fry",
            "salad",
            "sandwich-wrap",
            "sourdough",
        ],
        "effort_time": [
            "quick-weeknight",
            "low-effort",
            "weekend-project",
            "make-ahead",
        ],
        "occasion_utility": [
            "meal-prep",
            "freezer-friendly",
            "kid-friendly",
            "comfort-food",
            "light-fresh",
            "crowd-pleaser",
        ],
        "cuisine": [
            "italian",
            "mexican-texmex",
            "east-asian",
            "southeast-asian",
            "indian-south-asian",
            "mediterranean-greek",
            "middle-eastern",
            "american-classic",
            "french",
        ],
        "dietary": [
            "gluten-free",
            "dairy-free",
            "low-carb",
            "nut-free",
        ],
    },
}

# Categories eligible for Dinner Decider
DINNER_ELIGIBLE_CATEGORIES = {"dinner", "soup & stew", "soup-stew"}

# Badges and UI Emoji mappings for tags and tools
BADGE_ICONS = {
    # Tools
    "air fryer": ("💨", "Air Fryer"),
    "slow cooker": ("⏳", "Slow Cooker"),
    "instant pot": ("⚡", "Instant Pot"),
    "sheet pan": ("🥘", "Sheet Pan"),
    "cast iron skillet": ("🍳", "Cast Iron"),
    "dutch oven": ("🍲", "Dutch Oven"),
    "grill": ("🔥", "Grill"),
    "wok": ("🥢", "Wok"),
    # Effort
    "quick-weeknight": ("⚡", "Quick"),
    "low-effort": ("🛋️", "Easy"),
    "weekend-project": ("👨‍🍳", "Project"),
    # Occasion
    "comfort-food": ("🧀", "Comfort"),
    "light-fresh": ("🥗", "Fresh"),
    "kid-friendly": ("👶", "Kid-Friendly"),
    # Cuisines
    "italian": ("🍝", "Italian"),
    "mexican-texmex": ("🌮", "Mexican"),
    "east-asian": ("🥢", "East Asian"),
    "southeast-asian": ("🍜", "SE Asian"),
    "indian-south-asian": ("🍛", "Indian"),
    "mediterranean-greek": ("🫒", "Mediterranean"),
    "middle-eastern": ("🥙", "Middle Eastern"),
    "american-classic": ("🍔", "American"),
    "french": ("🥖", "French"),
    # Dietary
    "gluten-free": ("🌾", "Gluten-Free"),
    "dairy-free": ("🥛", "Dairy-Free"),
    "low-carb": ("🥑", "Low-Carb"),
}


def normalize_str(s: Any) -> str:
    """Normalize string for robust slug/tag comparison."""
    if not s:
        return ""
    return str(s).strip().lower().replace("_", "-").replace(" ", "-")


def extract_recipe_taxonomy(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """Parse recipeCategory, tags, and tools from a Mealie recipe object."""
    # 1. Categories
    raw_categories = recipe.get("recipeCategory") or recipe.get("categories") or []
    categories: Set[str] = set()
    for cat in raw_categories:
        if isinstance(cat, dict):
            categories.add(normalize_str(cat.get("slug") or cat.get("name")))
        elif isinstance(cat, str):
            categories.add(normalize_str(cat))

    # 2. Tools
    raw_tools = recipe.get("tools") or []
    tools: Set[str] = set()
    tool_names: List[str] = []
    for t in raw_tools:
        if isinstance(t, dict):
            slug = normalize_str(t.get("slug") or t.get("name"))
            tools.add(slug)
            tool_names.append(t.get("name") or slug)
        elif isinstance(t, str):
            slug = normalize_str(t)
            tools.add(slug)
            tool_names.append(t)

    # 3. Tags
    raw_tags = recipe.get("tags") or []
    tags: Set[str] = set()
    tag_names: List[str] = []
    for tag in raw_tags:
        if isinstance(tag, dict):
            slug = normalize_str(tag.get("slug") or tag.get("name"))
            tags.add(slug)
            tag_names.append(tag.get("name") or slug)
        elif isinstance(tag, str):
            slug = normalize_str(tag)
            tags.add(slug)
            tag_names.append(tag)

    # Dimension classification
    dimensions: Dict[str, List[str]] = {}
    for dim_name, dim_values in TAXONOMY["tag_dimensions"].items():
        matched = []
        for val in dim_values:
            val_norm = normalize_str(val)
            if val_norm in tags:
                matched.append(val_norm)
        dimensions[dim_name] = matched

    # Generate display badges (up to 3 concise, visually rich badges)
    badges = []
    seen_badges = set()

    # Tool badge (if any)
    for tool_slug in tools:
        clean_key = tool_slug.replace("-", " ")
        if clean_key in BADGE_ICONS and clean_key not in seen_badges:
            ico, lbl = BADGE_ICONS[clean_key]
            badges.append({"icon": ico, "label": lbl, "type": "tool"})
            seen_badges.add(clean_key)
            break

    # Cuisine badge (if any)
    for c in dimensions.get("cuisine", []):
        if c in BADGE_ICONS and c not in seen_badges:
            ico, lbl = BADGE_ICONS[c]
            badges.append({"icon": ico, "label": lbl, "type": "cuisine"})
            seen_badges.add(c)
            break

    # Effort / Occasion badge
    for e in dimensions.get("effort_time", []) + dimensions.get("occasion_utility", []):
        if e in BADGE_ICONS and e not in seen_badges:
            ico, lbl = BADGE_ICONS[e]
            badges.append({"icon": ico, "label": lbl, "type": "vibe"})
            seen_badges.add(e)
            if len(badges) >= 3:
                break

    # Dietary badge (e.g. GF)
    for d in dimensions.get("dietary", []):
        if d in BADGE_ICONS and d not in seen_badges and len(badges) < 3:
            ico, lbl = BADGE_ICONS[d]
            badges.append({"icon": ico, "label": lbl, "type": "dietary"})
            seen_badges.add(d)

    return {
        "categories": categories,
        "tools": tools,
        "tags": tags,
        "dimensions": dimensions,
        "primary_protein": dimensions["protein"][0] if dimensions.get("protein") else "other",
        "badges": badges[:3],
    }


def is_dinner_recipe(tax: Dict[str, Any]) -> bool:
    """Check if recipe belongs to Dinner (or Soup & Stew).

    If the user has not categorized recipes yet, allow uncategorized.
    """
    cats = tax.get("categories", set())
    if not cats:
        # If no categories assigned at all, don't exclude
        return True

    # If categorized, must match Dinner or Soup & Stew
    for c in cats:
        if c in DINNER_ELIGIBLE_CATEGORIES or "dinner" in c or "soup" in c:
            return True
    return False


SIDE_ELIGIBLE_CATEGORIES = {
    "side dish",
    "side-dish",
    "side",
    "appetizer & snack",
    "appetizer-snack",
    "salad",
    "vegetable",
    "vegetables",
}


def is_side_recipe(tax: Dict[str, Any], recipe: Optional[Dict[str, Any]] = None) -> bool:
    """Check if recipe belongs to Side Dish, Salad, or Vegetable category/tags."""
    cats = tax.get("categories", set())
    for c in cats:
        if c in SIDE_ELIGIBLE_CATEGORIES or "side" in c or "salad" in c:
            return True
    tags = tax.get("tags", set())
    if any(t in ("side", "side-dish", "vegetables", "salad", "appetizer") for t in tags):
        return True
    if recipe:
        title = str(recipe.get("name", "")).lower()
        side_keywords = [
            "salad",
            "potato",
            "potatoes",
            "fries",
            "rice",
            "asparagus",
            "green bean",
            "green beans",
            "broccoli",
            "garlic bread",
            "slaw",
            "coleslaw",
            "roasted veg",
            "corn on the cob",
            "mac and cheese",
            "baked beans",
            "cauliflower",
            "zucchini",
            "brussels sprout",
        ]
        if any(k in title for k in side_keywords):
            return True
    return False


def select_side_recipes(
    recipes: List[Dict[str, Any]],
    count: int = 3,
) -> List[Dict[str, Any]]:
    """Select 'count' diverse side dish recipes."""
    if not recipes:
        return []

    side_candidates = []
    for r in recipes:
        tax = r.get("_taxonomy") or extract_recipe_taxonomy(r)
        r["_taxonomy"] = tax
        if is_side_recipe(tax, r):
            side_candidates.append(r)

    if not side_candidates:
        return []

    if len(side_candidates) <= count:
        return side_candidates

    random.shuffle(side_candidates)
    return side_candidates[:count]


def matches_filter(
    tax: Dict[str, Any],
    recipe: Dict[str, Any],
    mood: Optional[str] = None,
    protein: Optional[str] = None,
    tool: Optional[str] = None,
    cuisine: Optional[str] = None,
) -> bool:
    """Determine whether a recipe satisfies the active mood or dimension filters."""
    tags = tax.get("tags", set())
    tools = tax.get("tools", set())
    dims = tax.get("dimensions", {})

    # 1. Specific Protein filter
    if protein:
        p_norm = normalize_str(protein)
        if p_norm not in dims.get("protein", []):
            return False

    # 2. Specific Tool filter
    if tool:
        t_norm = normalize_str(tool)
        if t_norm not in tools:
            return False

    # 3. Specific Cuisine filter
    if cuisine:
        c_norm = normalize_str(cuisine)
        if c_norm not in dims.get("cuisine", []):
            return False

    # 4. Mood Preset filter
    if mood:
        m = normalize_str(mood)
        if m in ("quick", "quick-weeknight"):
            # Matches quick-weeknight tag, low-effort tag, or <= 30 mins
            total_time = str(recipe.get("totalTime", "")).lower()
            is_fast = "20" in total_time or "25" in total_time or "30" in total_time or "15" in total_time
            if not ("quick-weeknight" in tags or "low-effort" in tags or is_fast):
                return False
        elif m in ("comfort", "comfort-food"):
            if "comfort-food" not in tags and "baked-casserole" not in tags:
                return False
        elif m in ("fresh", "light-fresh"):
            if "light-fresh" not in tags and "salad" not in tags:
                return False
        elif m in ("one-pot", "one-pot-meals"):
            if "one-pot" not in tags and "sheet-pan" not in tags and "skillet" not in tags:
                return False
        elif m in ("air-fryer", "airfryer"):
            if "air-fryer" not in tools:
                return False
        elif m in ("slow-cooker", "slowcooker"):
            if "slow-cooker" not in tools:
                return False
        elif m in ("sheet-pan", "sheetpan"):
            if "sheet-pan" not in tools and "sheet-pan" not in tags:
                return False
        elif m == "chicken":
            if "chicken" not in dims.get("protein", []):
                return False
        elif m == "beef":
            if "beef" not in dims.get("protein", []):
                return False
        elif m == "seafood":
            if "seafood" not in dims.get("protein", []):
                return False
        elif m in ("vegetarian", "veggie"):
            if not any(v in dims.get("protein", []) for v in ["vegetarian", "vegan", "beans-legumes", "tofu-tempeh", "pasta-noodles"]):
                return False

    return True


def select_balanced_recipes(
    recipes: List[Dict[str, Any]],
    count: int = 3,
    mood: Optional[str] = None,
    protein: Optional[str] = None,
    tool: Optional[str] = None,
    cuisine: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Select 'count' recipes with maximum protein and cuisine diversity."""
    if not recipes:
        return []

    # Filter for dinner category eligibility
    dinner_candidates = []
    for r in recipes:
        tax = r.get("_taxonomy") or extract_recipe_taxonomy(r)
        r["_taxonomy"] = tax
        if is_dinner_recipe(tax):
            dinner_candidates.append(r)

    # Fall back if no dinner categories tagged
    if not dinner_candidates:
        dinner_candidates = recipes

    # Apply user active filter/mood
    filtered = []
    for r in dinner_candidates:
        tax = r["_taxonomy"]
        if matches_filter(tax, r, mood=mood, protein=protein, tool=tool, cuisine=cuisine):
            filtered.append(r)

    # If filtered pool has matches, honor the user's specific filter.
    # If completely empty, fall back to dinner_candidates so choices are never blank.
    pool = filtered if len(filtered) > 0 else dinner_candidates
    if len(pool) <= count:
        return pool

    # Day-of-week context weighting (Mon-Thu vs Fri-Sun)
    weekday = date.today().weekday()  # 0=Monday, 6=Sunday
    is_weeknight = weekday in (0, 1, 2, 3)

    # Group pool by protein families for anti-monotony
    # Group A: Poultry (chicken, turkey)
    # Group B: Red Meat & Seafood (beef, pork, seafood, lamb)
    # Group C: Plant-based & Pasta (vegetarian, vegan, beans-legumes, tofu-tempeh, pasta-noodles, egg, other)
    groups: Dict[str, List[Dict[str, Any]]] = {"poultry": [], "red_seafood": [], "plant_other": []}

    for r in pool:
        p = r["_taxonomy"]["primary_protein"]
        if p in ("chicken", "turkey"):
            groups["poultry"].append(r)
        elif p in ("beef", "pork", "seafood", "lamb"):
            groups["red_seafood"].append(r)
        else:
            groups["plant_other"].append(r)

    # If weeknight, sort each group to prioritize quick/low-effort recipes first
    if is_weeknight:
        for g_name in groups:
            groups[g_name].sort(
                key=lambda x: (
                    0 if "quick-weeknight" in x["_taxonomy"]["tags"] or "low-effort" in x["_taxonomy"]["tags"] else 1,
                    random.random(),
                )
            )
    else:
        for g_name in groups:
            random.shuffle(groups[g_name])

    selected: List[Dict[str, Any]] = []
    available_group_keys = [k for k, v in groups.items() if len(v) > 0]
    random.shuffle(available_group_keys)

    # Pick 1 from each distinct protein group first
    for g_key in available_group_keys:
        if len(selected) >= count:
            break
        if groups[g_key]:
            chosen = groups[g_key].pop(0)
            selected.append(chosen)

    # If still need more, fill from remaining pool with distinct recipes
    if len(selected) < count:
        remaining = [r for r in pool if r not in selected]
        random.shuffle(remaining)
        needed = count - len(selected)
        selected.extend(remaining[:needed])

    random.shuffle(selected)
    return selected
