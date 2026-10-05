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
DINNER_ELIGIBLE_CATEGORIES = {
    "dinner",
    "soup & stew",
    "soup-&-stew",
    "soup-stew",
    "soup",
}

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
    # Cooking Style
    "skillet": ("🍳", "Skillet"),
    "one-pot": ("🍲", "One-Pot"),
    "sheet-pan": ("🥘", "Sheet Pan"),
    "grill-bbq": ("🔥", "Grill"),
    "baked-casserole": ("🥧", "Casserole"),
    "stir-fry": ("🥢", "Stir-Fry"),
    "pasta-noodles": ("🍝", "Pasta"),
    "salad": ("🥗", "Salad"),
    "sandwich-wrap": ("🥪", "Sandwich"),
    "no-cook": ("🥗", "No-Cook"),
    # Effort / Time
    "quick-weeknight": ("⚡", "Quick"),
    "low-effort": ("🛋️", "Easy"),
    "weekend-project": ("👨‍🍳", "Project"),
    "make-ahead": ("⏱️", "Make-Ahead"),
    # Occasion / Utility
    "comfort-food": ("🧀", "Comfort"),
    "light-fresh": ("🥗", "Fresh"),
    "kid-friendly": ("👶", "Kid-Friendly"),
    "crowd-pleaser": ("🎉", "Crowd-Pleaser"),
    "meal-prep": ("🍱", "Meal Prep"),
    "freezer-friendly": ("❄️", "Freezer"),
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
    "vegetarian": ("🌱", "Vegetarian"),
    "vegan": ("🌿", "Vegan"),
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

    # Cooking Style badge (if any)
    for s in dimensions.get("cooking_style", []):
        if s in BADGE_ICONS and s not in seen_badges:
            ico, lbl = BADGE_ICONS[s]
            badges.append({"icon": ico, "label": lbl, "type": "style"})
            seen_badges.add(s)
            if len(badges) >= 3:
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

    # Pantry stock badge (if _pantry metadata is attached)
    pantry_info = recipe.get("_pantry")
    if pantry_info:
        status = pantry_info.get("status")
        missing_count = pantry_info.get("missing_count", 0)
        missing_items = pantry_info.get("missing_items", [])
        missing_perishables = pantry_info.get("missing_perishables", [])
        missing_anchor = pantry_info.get("missing_anchor")

        if status == "ready" or (status is None and missing_count == 0):
            badges.insert(0, {"icon": "🟢", "label": "Ready to Cook", "type": "pantry"})
        elif status == "almost_ready" or (status is None and missing_count in (1, 2)):
            target_item = missing_perishables[0] if missing_perishables else (missing_items[0] if missing_items else "1 item")
            short_lbl = target_item if len(target_item) <= 16 else target_item[:15] + "…"
            badges.insert(0, {"icon": "🟡", "label": f"Need: {short_lbl}", "type": "pantry"})
        else:
            if missing_anchor:
                short_anchor = missing_anchor if len(missing_anchor) <= 14 else missing_anchor[:13] + "…"
                badges.insert(0, {"icon": "⚪", "label": f"No {short_anchor}", "type": "pantry"})
            else:
                badges.insert(0, {"icon": "⚪", "label": f"{missing_count} Missing", "type": "pantry"})

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

    Strictly excludes recipes categorized as Side Dish.
    If the user has not categorized recipes yet, allow uncategorized.
    """
    cats = tax.get("categories", set())
    # Exclude any recipe explicitly designated as a side
    if any(c in SIDE_ELIGIBLE_CATEGORIES or "side" in c for c in cats):
        return False

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
}


def is_side_recipe(tax: Dict[str, Any], recipe: Optional[Dict[str, Any]] = None) -> bool:
    """Check if recipe belongs to Side Dish category.

    Strictly ensures main dinner recipes (even with salad/potato tags) are never classified as sides.
    """
    cats = tax.get("categories", set())

    # 1. If explicitly categorized as Dinner, it is a main course, NOT a side
    if any(c in DINNER_ELIGIBLE_CATEGORIES or "dinner" in c for c in cats):
        return False

    # 2. Match explicit Side Dish category
    for c in cats:
        if c in SIDE_ELIGIBLE_CATEGORIES or "side" in c:
            return True

    # 3. If explicit side tag is present (and not dinner)
    tags = tax.get("tags", set())
    if any(t in ("side", "side-dish") for t in tags):
        return True

    # 4. Keyword fallback ONLY if recipe is completely uncategorized
    if not cats:
        protein_tags = {"chicken", "beef", "pork", "seafood", "lamb", "turkey"}
        if tags.intersection(protein_tags):
            return False

        if recipe:
            title = str(recipe.get("name", "")).lower()
            side_keywords = [
                "coleslaw",
                "slaw",
                "green bean",
                "green beans",
                "garlic bread",
                "mashed potato",
                "roasted potato",
                "french fries",
                "roasted veg",
                "brussels sprout",
            ]
            if any(k in title for k in side_keywords):
                return True

    return False


def classify_side_bucket(recipe: Dict[str, Any], tax: Dict[str, Any]) -> str:
    """Classify a side recipe into 'salad', 'starch', or 'veggie'."""
    tags = tax.get("tags", set())
    title = str(recipe.get("name", "")).lower()

    # 1. Starches, Potatoes & Grains
    starch_keywords = [
        "potato",
        "potatoes",
        "rice",
        "hash brown",
        "fries",
        "naan",
        "bread",
        "pasta",
        "grain",
        "quinoa",
        "corn",
    ]
    if any(k in title for k in starch_keywords):
        return "starch"

    # 2. Fresh Salads & Slaws
    if "salad" in tags or "no-cook" in tags or "slaw" in title or "salad" in title:
        return "salad"

    # 3. Warm Roasted & Sautéed Veggies
    return "veggie"


def select_side_recipes(
    recipes: List[Dict[str, Any]],
    count: int = 3,
) -> List[Dict[str, Any]]:
    """Select 'count' diverse side dish recipes, ideally 1 salad, 1 starch, 1 veggie."""
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

    # Partition candidates into 3 distinct culinary buckets:
    # 1. Fresh Salads & Slaws
    # 2. Potatoes, Grains & Starches
    # 3. Warm Roasted & Sautéed Veggies
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "salad": [],
        "starch": [],
        "veggie": [],
    }
    for r in side_candidates:
        b = classify_side_bucket(r, r["_taxonomy"])
        buckets[b].append(r)

    for b in buckets:
        random.shuffle(buckets[b])

    selected: List[Dict[str, Any]] = []

    # Pick 1 from each bucket if available
    for b in ("salad", "starch", "veggie"):
        if buckets[b] and len(selected) < count:
            selected.append(buckets[b].pop(0))

    # If we still need more to satisfy count (e.g. one bucket was empty), fill from remaining pool
    if len(selected) < count:
        remaining = [r for r in side_candidates if r not in selected]
        random.shuffle(remaining)
        needed = count - len(selected)
        selected.extend(remaining[:needed])

    random.shuffle(selected)
    return selected


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
    title = str(recipe.get("name", "")).lower()

    # 1. Specific Protein filter
    if protein:
        p_norm = normalize_str(protein)
        if p_norm in ("vegetarian", "veggie"):
            if not any(v in dims.get("protein", []) or v in tags for v in ["vegetarian", "vegan", "beans-legumes", "tofu-tempeh"]):
                return False
        elif p_norm not in dims.get("protein", []) and p_norm not in tags:
            return False

    # 2. Specific Tool filter
    if tool:
        t_norm = normalize_str(tool)
        if t_norm not in tools and t_norm not in tags:
            return False

    # 3. Specific Cuisine filter
    if cuisine:
        c_norm = normalize_str(cuisine)
        if c_norm in ("asian", "east-asian", "southeast-asian"):
            asian_cuisines = {"east-asian", "southeast-asian"}
            if not any(ac in dims.get("cuisine", []) or ac in tags for ac in asian_cuisines):
                return False
        elif c_norm not in dims.get("cuisine", []) and c_norm not in tags:
            return False

    # 4. Mood Preset filter
    if mood:
        m = normalize_str(mood)
        if m in ("quick", "quick-weeknight"):
            # Matches quick-weeknight tag, low-effort tag, or <= 30 mins
            total_time = str(recipe.get("totalTime", "")).lower()
            is_fast = any(t in total_time for t in ["15", "20", "25", "30"])
            if not ("quick-weeknight" in tags or "low-effort" in tags or is_fast):
                return False
        elif m in ("comfort", "comfort-food"):
            if "comfort-food" not in tags and "baked-casserole" not in tags:
                return False
        elif m in ("fresh", "light-fresh"):
            if "light-fresh" not in tags and "salad" not in tags:
                return False
        elif m in ("skillet", "cast-iron"):
            if "skillet" not in tags and "cast-iron-skillet" not in tools:
                return False
        elif m in ("one-pot", "one-pot-meals"):
            if "one-pot" not in tags and "dutch-oven" not in tools:
                return False
        elif m in ("sheet-pan", "sheetpan"):
            if "sheet-pan" not in tools and "sheet-pan" not in tags:
                return False
        elif m in ("grill", "grill-bbq", "bbq"):
            if "grill-bbq" not in tags and "grill" not in tools:
                return False
        elif m in ("pasta", "pasta-noodles"):
            if "pasta-noodles" not in tags and not any(k in title for k in ["pasta", "spaghetti", "noodle", "orzo", "risoni"]):
                return False
        elif m == "chicken":
            if "chicken" not in dims.get("protein", []) and "chicken" not in tags:
                return False
        elif m == "beef":
            if "beef" not in dims.get("protein", []) and "beef" not in tags:
                return False
        elif m == "pork":
            if "pork" not in dims.get("protein", []) and "pork" not in tags:
                return False
        elif m == "seafood":
            if "seafood" not in dims.get("protein", []) and "seafood" not in tags:
                return False
        elif m in ("vegetarian", "veggie"):
            if not any(v in dims.get("protein", []) or v in tags for v in ["vegetarian", "vegan", "beans-legumes", "tofu-tempeh"]):
                return False
        elif m in ("asian", "east-asian", "southeast-asian"):
            if not any(ac in dims.get("cuisine", []) or ac in tags for ac in ["east-asian", "southeast-asian"]):
                return False
        elif m == "italian":
            if "italian" not in dims.get("cuisine", []) and "italian" not in tags:
                return False
        elif m in ("mexican", "mexican-texmex"):
            if "mexican-texmex" not in dims.get("cuisine", []) and "mexican-texmex" not in tags:
                return False
        elif m in ("air-fryer", "airfryer"):
            if "air-fryer" not in tools:
                return False
        elif m in ("slow-cooker", "slowcooker"):
            if "slow-cooker" not in tools:
                return False
        elif m in ("pantry", "pantry-ready"):
            pantry_info = recipe.get("_pantry")
            if pantry_info is not None and not pantry_info.get("is_ready", False):
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

    # Base sampling weights: on weeknights, gently favor quick/low-effort recipes (1.8x boost)
    # instead of a deterministic sort that starves variety or locks in a single recipe
    base_weights = []
    for r in pool:
        tags = r["_taxonomy"]["tags"]
        is_quick = "quick-weeknight" in tags or "low-effort" in tags
        w = 1.8 if (is_weeknight and is_quick) else 1.0

        p_info = r.get("_pantry")
        if p_info:
            if p_info.get("status") == "ready":
                w *= 1.6
            elif p_info.get("status") == "almost_ready":
                w *= 1.2
            elif not p_info.get("is_ready", True):
                w *= 0.2

        base_weights.append(w)

    selected: List[Dict[str, Any]] = []
    selected_proteins: Set[str] = set()
    selected_cuisines: Set[str] = set()
    available_indices = list(range(len(pool)))

    # Iteratively choose recipes, dynamically discounting already-represented proteins and cuisines
    while len(selected) < count and available_indices:
        current_weights = []
        for idx in available_indices:
            r = pool[idx]
            prot = r["_taxonomy"]["primary_protein"]
            cuisines = r["_taxonomy"]["dimensions"].get("cuisine", [])
            w = base_weights[idx]

            # Anti-monotony penalty for duplicate protein family
            if prot in selected_proteins:
                w *= 0.15
            # Soft penalty for duplicate cuisine
            if any(c in selected_cuisines for c in cuisines):
                w *= 0.5
            current_weights.append(w)

        # Weighted probabilistic choice
        chosen_idx = random.choices(available_indices, weights=current_weights, k=1)[0]
        chosen = pool[chosen_idx]
        selected.append(chosen)

        # Track selected dimensions
        selected_proteins.add(chosen["_taxonomy"]["primary_protein"])
        for c in chosen["_taxonomy"]["dimensions"].get("cuisine", []):
            selected_cuisines.add(c)
        available_indices.remove(chosen_idx)

    random.shuffle(selected)
    return selected
