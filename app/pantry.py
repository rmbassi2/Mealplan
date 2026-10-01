"""Pantry Inventory Management & Recipe Matching Engine.

Provides lightweight, zero-friction ingredient availability tracking
using an embedded SQLite database. Evaluates whether recipes are 100%
pantry-ready or at most 1 ingredient away.
"""

import logging
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings

logger = logging.getLogger("pantry")

# Default common kitchen staples that do not count as missing ingredients
DEFAULT_STAPLES: Set[str] = {
    "salt",
    "kosher salt",
    "sea salt",
    "table salt",
    "pepper",
    "black pepper",
    "freshly ground black pepper",
    "ground black pepper",
    "cracked pepper",
    "water",
    "tap water",
    "ice water",
    "olive oil",
    "extra virgin olive oil",
    "extra-virgin olive oil",
    "cooking oil",
    "vegetable oil",
    "canola oil",
    "cooking spray",
    "sugar",
    "granulated sugar",
    "white sugar",
    "brown sugar",
    "flour",
    "all-purpose flour",
}

# Measurement words and culinary stop words to strip during string cleaning
MEASUREMENT_WORDS = re.compile(
    r"\b(\d+([./]\d+)?|\d+-\d+)\s*"
    r"(cups?|tbsp|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|kg|"
    r"ml|liters?|cloves?|slices?|pinch(es)?|dash(es)?|cans?|jars?|packages?|pkgs?|"
    r"heads?|bunches?|stalks?|pieces?)\b",
    re.IGNORECASE,
)

UNIT_WORDS = re.compile(
    r"\b(cups?|c\.|c\b|tbsp|tbs|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|kg|"
    r"ml|liters?|litres?|cloves?|slices?|pinch(es)?|dash(es)?|cans?|jars?|packages?|pkgs?|"
    r"heads?|bunches?|stalks?|pieces?|sprigs?|handfuls?)\b",
    re.IGNORECASE,
)

PREP_WORDS = re.compile(
    r"\b(organic|diced|chopped|minced|sliced|crushed|grated|shredded|melted|softened|"
    r"warm|cold|fresh|freshly|dried|ground|boneless|skinless|cooked|uncooked|"
    r"to taste|divided|optional|room temperature)\b",
    re.IGNORECASE,
)

FRACTION_MAP: Dict[str, str] = {
    "¼": " 1/4 ", "½": " 1/2 ", "¾": " 3/4 ",
    "⅓": " 1/3 ", "⅔": " 2/3 ",
    "⅛": " 1/8 ", "⅜": " 3/8 ", "⅝": " 5/8 ", "⅞": " 7/8 ",
    "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "₁": "1", "₂": "2", "₃": "3", "₄": "4",
}

DISCARD_PATTERNS = [
    re.compile(r"could\s+not\s+detect", re.I),
    re.compile(r"unable\s+to\s+detect", re.I),
    re.compile(r"check\s+the\s+notes?", re.I),
    re.compile(r"^\s*\*{2,}", re.I),
    re.compile(r"recommend\s+doubling", re.I),
    re.compile(r"^other\s+ideas\b", re.I),
    re.compile(r"^tips?\s*:", re.I),
    re.compile(r"^substitutions?\s*:", re.I),
    re.compile(r"^variations?\s*:", re.I),
    re.compile(r"^instructions?\s*:", re.I),
    re.compile(r"^directions?\s*:", re.I),
    re.compile(r"^step\s*\d+", re.I),
    re.compile(r"^for\s+greasing\b", re.I),
    re.compile(r"^recipe\s+(guacamole|pico\s+de\s+gallo)\b", re.I),
    re.compile(r"for\s+serving,?\s+if\s+desired", re.I),
    re.compile(r"^vegetables?\s+of\s+choice", re.I),
    re.compile(r"^skewers?\b", re.I),
    re.compile(r"^pound\s+peeled,?\s+i\s+use", re.I),
]

PREP_WORDS_PATTERN = (
    r"\b(finely|coarsely|roughly|thinly|fresh-squeezed|squeezed|freshly|fresh|lightly|"
    r"chopped|diced|minced|sliced|crushed|grated|shredded|peeled|halved|quartered|"
    r"drained|juiced|zested|cooked|uncooked|packed|melted|softened|warm|cold|hot|"
    r"trimmed|cored|stemmed|cleaned|thawed|cut\s+into|cut\s+in|boneless|skinless|"
    r"organic|dried|cloves?|unsalted|salted)\b"
)
PREP_REGEX = re.compile(PREP_WORDS_PATTERN, re.I)

PREP_TRAILING_CHECK = re.compile(
    r"\b(cut|peeled|sliced|chopped|diced|minced|grated|shredded|crushed|cored|"
    r"stem|halved|quartered|drained|juiced|zested|cooked|thawed|trimmed|cleaned|"
    r"packed|finely|roughly|coarsely|lightly|plus|for garnish|for serving|to serve|"
    r"to taste|divided|optional|not spicy|any brand|brand fine|seeds removed|about|"
    r"browned|room temp|room temperature|warmed up|softened|melted|cubed|very cold)\b",
    re.I,
)

FOOD_NOUN_CHECK = re.compile(
    r"\b(chicken|beef|pork|lamb|turkey|meat|fish|shrimp|salmon|tuna|steak|bacon|sausage|"
    r"onion|garlic|tomato|potato|carrot|cabbage|pepper|chile|zucchini|cucumber|"
    r"basil|parsley|cilantro|rosemary|thyme|sage|dill|lemon|lime|spinach|lettuce|"
    r"beans|lentils|rice|pasta|noodle|spaghetti|cheese|milk|cream|butter|yogurt|"
    r"broth|stock|oil|flour|sugar|sauce|powder|spice|curry|sprouts|ginger|fillets?|"
    r"pecans?|walnuts?|almonds?|cashews?|peanuts?|tofu|paneer|oats?|bread|bun|buns)\b",
    re.I,
)

UNIT_PREFIX_REGEX = re.compile(
    r"^\s*(?:"
    r"(\d+(\.\d+)?\s*[-–—/]\s*\d+(\.\d+)?|\d+([./]\d+)?)\s*|"
    r"(th|rd|st|nd)\s+|"
    r"(\d+(\.\d+)?\s*)?(gm|g|grams?|kg|kgs|kilos?|ml|mls|milliliters?|litres?|liters?|l)\b\/?\/?\s*|"
    r"(\d+(\.\d+)?\s*)?(cups?|c\.|c|tbsp|tbs|tablespoons?|tsp|teaspoons?|t)\b\s*|"
    r"(\d+(\.\d+)?\s*)?(lbs?|lb\.|pounds?|oz|oz\.|ounces?)\b\/?\/?\s*|"
    r"(\d+(\.\d+)?\s*)?(cans?|jars?|pkgs?|packages?|heads?|bunches?|bunch|stalks?|pieces?|piece|sprigs?|springs?|handfuls?|sticks?|stick|quarts?|qt|gallons?|gal|containers?|container|box(?:es)?|bottles?|knobs?|slices?|cloves?|ribs?)\b\s*|"
    r"(pinch(?:es)?|tiny\s+pinch|dash(?:es)?)\b\s*(?:of\s+)?|"
    r"(large|medium|small|medium-small|extra-large|xl|big|tiny|inch(?:es)?|knob)\b\s*|"
    r"(x|of|about|or|and|plus|with)\b\s*|"
    r"i\s+use\b\s*|"
    r"\/\s*\d+(\.\d+)?\s*(kg|g|gm|lb|lbs|oz|ml|l)\b\s*"
    r")",
    re.I,
)

PLURAL_MAP: Dict[str, str] = {
    "tomatoes": "tomato",
    "potatoes": "potato",
    "onions": "onion",
    "carrots": "carrot",
    "cucumbers": "cucumber",
    "limes": "lime",
    "lemons": "lemon",
    "cloves": "garlic",
}


def is_staple_ingredient(norm: str, raw: str = "") -> bool:
    """Identify common staples like salt, pepper, water, pan spray, plain sugar, and flour."""
    n = norm.lower().strip()
    r = raw.lower().strip() if raw else ""

    # 1. Salt variants: salt present, but not salt pork, salt cod, salted pretzels, salted caramel
    if "salt" in n or "salt" in r:
        if not any(k in n or k in r for k in ["pork", "cod", "beef", "pretzel", "caramel", "cracker", "butter"]):
            return True

    # 2. Pepper (black/white/ground pepper, cracked pepper - not bell pepper, chile pepper, cayenne)
    if "pepper" in n or "pepper" in r:
        if any(k in n or k in r for k in ["black pepper", "white pepper", "ground pepper", "freshly ground pepper", "cracked pepper", "ground black pepper"]) or n in ("pepper", "salt and pepper", "salt & pepper"):
            return True

    # 3. Water variants: plain water, filtered, ice cubes (not watermelon, coconut water, etc.)
    if "water" in n or "ice cubes" in n or "water" in r or "ice cubes" in r:
        if not any(k in n or k in r for k in ["chestnut", "melon", "coconut", "cress", "rose"]):
            return True

    # 4. Cooking spray / pan greasing
    if any(k in n or k in r for k in ["cooking spray", "vegetable spray", "greasing"]):
        return True

    # 5. Plain sugar (not brown sugar, coconut sugar, confectioners sugar)
    if n in ("sugar", "granulated sugar", "white sugar", "white granulated sugar"):
        return True

    # 6. Plain all-purpose flour
    if n in ("all purpose flour", "all-purpose flour", "plain flour", "unbleached all purpose flour"):
        return True

    return False


def clean_ingredient_name(raw: str) -> Optional[Tuple[str, str]]:
    """Sanitize messy scraped recipe ingredient strings into clean canonical names and display labels.

    Returns (normalized_name, display_name) or None if discarded.
    """
    if not raw or not raw.strip():
        return None

    # 1. Discard non-ingredient instructions, scraper errors, or blog notes
    for pat in DISCARD_PATTERNS:
        if pat.search(raw):
            return None

    text = raw.strip()

    # Strip trailing pipe or noise
    text = re.sub(r"[\s\|\&\+]+$", "", text)

    # 2. Normalize fractions (vulgar fractions, superscripts/subscripts)
    for k, v in FRACTION_MAP.items():
        text = text.replace(k, v)
    text = re.sub(r"¹\s*\/\s*₂", " 1/2 ", text)

    # 3. Strip leading noise characters: (), [], ., /, -, *, &, +, |, (Or ), (And )
    text = re.sub(r"^[\s\(\)\[\]\.\/\,\-\*\:\;\#\~\&\+\|]+", "", text)
    text = re.sub(r"^\(?\s*or\b\s*\)?\s*", "", text, flags=re.I)
    text = re.sub(r"^\(?\s*and\b\s*\)?\s*", "", text, flags=re.I)
    text = re.sub(r"^optional\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^(?:fresh-squeezed|-squeezed|squeezed|ly\s+)\s*", "", text, flags=re.I)

    # Normalize "juice from 2 lemons" -> "lemon juice"
    text = re.sub(r"^juice\s+(of|from)\s+(\d+\s*)?lemons?", "lemon juice", text, flags=re.I)
    text = re.sub(r"^juice\s+(of|from)\s+(\d+\s*)?limes?", "lime juice", text, flags=re.I)

    # 4. Remove empty parens/brackets
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\[\s*\]", " ", text)

    # 5. Remove parenthetical expressions (notes, measurements, preps)
    while "(" in text and ")" in text:
        new_text = re.sub(r"\([^()]*\)", " ", text)
        if new_text == text:
            break
        text = new_text

    # Strip unmatched dangling parens
    text = re.sub(r"[()]", " ", text)

    # 6. Strip trailing prep and instructions after commas from the right
    parts = [p.strip() for p in text.split(",") if p.strip()]
    while len(parts) > 1:
        last = parts[-1]
        if PREP_TRAILING_CHECK.search(last) and not FOOD_NOUN_CHECK.search(last):
            parts.pop()
        else:
            break
    text = ", ".join(parts)

    # 7. Strip trailing notes and quantity alternatives
    text = re.sub(r"\s+or\b\s+(\d+\s*)?(large|medium|small|each)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+or\b\s+of\s+each\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+or\b\s+\.\s+each\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(for garnish|for serving|to serve|to taste|if desired|as needed|as desired)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(finely\s+chopped|finely\s+diced|coarsely\s+ground|thinly\s+sliced|minced|grated|peeled)\s*$", "", text, flags=re.I)

    # 8. Strip leading quantities, metric units, units, sizing, ordinals in a loop
    while True:
        prev = text
        text = UNIT_PREFIX_REGEX.sub("", text)
        text = re.sub(r"^[\s\.\,\/\-\:\;\&\+\|]+", "", text)
        if text == prev:
            break

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Discard if too short or lacking alphabetic substance
    if not re.search(r"[a-zA-Z]{2,}", text):
        return None

    # Discard if only a measurement unit word remains
    if re.fullmatch(r"(cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|ounces?|grams?|g|kg|ml|litres?|liters?|pinch|dash|c|t|lb|lbs|pound|pounds)", text, re.I):
        return None

    # Clean leading prep adjectives from display name for a clean UI presentation
    clean_display = text
    clean_display = re.sub(r"^(?:fresh-squeezed|-squeezed|squeezed|ly\s+)\s*", "", clean_display, flags=re.I)
    clean_display = re.sub(
        r"^(?:(finely|coarsely|roughly|thinly|freshly\b|fresh\b|lightly|packed|chopped|diced|minced|"
        r"grated|shredded|peeled|cooked|boneless|skinless|unsalted|salted|chopped\s+or\s+halved|halved|quartered|or\b)\s*,?\s*)+",
        "",
        clean_display,
        flags=re.I,
    ).strip()
    clean_display = re.sub(r"^[\s\-\,\.\:\;\/]+", "", clean_display)
    if not clean_display or len(clean_display) < 2:
        clean_display = text

    display = clean_display.title()
    if display in ("Garlic Cloves", "Large Garlic Cloves"):
        display = "Garlic"

    # Normalized name: lowercased, prep words and punctuation removed for grouping
    norm = text.lower()
    norm = re.sub(r"[-–—]", " ", norm)
    norm = PREP_REGEX.sub(" ", norm)
    norm = re.sub(r"[^\w\s]", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()

    # Singularize common end words for tighter grouping
    tokens = norm.split()
    if tokens:
        last_tok = tokens[-1]
        if last_tok in PLURAL_MAP:
            tokens[-1] = PLURAL_MAP[last_tok]
            norm = " ".join(tokens)

    if norm in ("cloves", "garlic cloves"):
        norm = "garlic"

    if not norm or len(norm) < 2:
        return None

    return norm, display


def normalize_ingredient_name(raw: str) -> str:
    """Clean and normalize an ingredient name for fuzzy matching."""
    cleaned = clean_ingredient_name(raw)
    if cleaned:
        return cleaned[0]
    return ""


def categorize_ingredient(name: str) -> str:
    """Smart heuristic categorization for pantry items."""
    n = name.lower()

    # 1. Spices & Seasonings
    if any(k in n for k in [
        "powder", "paprika", "cumin", "oregano", "cinnamon", "spice", "nutmeg",
        "curry", "seasoning", "coriander", "allspice", "cardamom", "clove",
        "turmeric", "cayenne", "chili flake", "red pepper flake", "mace", "peppercorn"
    ]) or re.search(r"\b(rubs?)\b", n):
        return "spices & herbs"

    # 2. Sauces & Condiments
    if any(k in n for k in [
        "broth", "stock", "bouillon", "boulion", "sauce", "vinegar", "hoisin",
        "peanut butter", "honey", "miso", "mustard", "mayo", "ketchup",
        "sriracha", "worcestershire", "tahini", "relish", "dressing", "syrup"
    ]):
        return "sauces & condiments"

    # 3. Dairy & Eggs
    if (
        any(k in n for k in [
            "milk", "cream", "cheese", "butter", "yogurt", "mozzarella", "parmesan",
            "cheddar", "feta", "boursin", "pecorino", "gruyere",
            "gruyère", "jack", "ricotta", "half-and-half", "buttermilk"
        ])
        or (re.search(r"\b(eggs?)\b", n) and "eggplant" not in n)
    ):
        return "dairy"

    # 4. Grains & Bakery
    if any(k in n for k in [
        "rice", "noodle", "pasta", "bread", "dough", "tortilla", "spaghetti",
        "orzo", "quinoa", "flour", "pita", "starter", "risotto",
        "crumbs", "cracker", "tagliatelle", "cereal"
    ]) or re.search(r"\b(buns?|rolls?|oats?|oatmeal)\b", n):
        return "grains & bakery"

    # 5. Protein
    if any(k in n for k in [
        "chicken", "beef", "pork", "steak", "turkey", "lamb", "bacon", "salmon",
        "shrimp", "fish", "tuna", "patty", "patties", "meat", "sausage", "chorizo",
        "pancetta", "guanciale", "prosciutto", "salami", "tofu", "paneer", "mince"
    ]) or re.search(r"\b(ham|cod)\b", n):
        return "protein"

    # 6. Produce & Fresh
    if any(k in n for k in [
        "tomato", "onion", "garlic", "spinach", "lettuce", "cilantro", "basil", "parsley",
        "lemon", "lime", "potato", "carrot", "broccoli", "zucchini", "cucumber", "cabbage",
        "sprouts", "sage", "rosemary", "chile", "chili", "peppers", "avocado", "herb",
        "mint", "scallion", "shallot", "leek", "celery", "fennel", "mushroom", "bean",
        "kale", "ginger", "cauliflower", "rhubarb", "edamame", "eggplant",
        "chive", "jalapeno", "jalapeño", "serrano", "romaine", "apple", "banana", "berry",
        "mango", "peach", "fruit", "slaw"
    ]) or re.search(r"\b(peas?|corn)\b", n):
        return "produce"

    return "pantry"


class PantryManager:
    """Manages pantry item persistence and recipe matching logic."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or getattr(settings, "pantry_db_path", "data/pantry.db")
        self._ensure_db_dir()
        self._in_stock_cache: Optional[Set[str]] = None
        self._cache_timestamp: float = 0.0
        self.init_db()

    def _ensure_db_dir(self):
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize pantry SQLite schema and perform automatic migrations."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pantry_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'pantry',
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    is_staple INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_name ON pantry_items (name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_in_stock ON pantry_items (in_stock)"
            )
            conn.commit()

        self.cleanup_existing_items()

    def cleanup_existing_items(self) -> int:
        """Sanitize, deduplicate, and remove staples/junk from existing SQLite rows in-place."""
        self._invalidate_cache()
        cleaned_count = 0
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id, name, display_name, category, in_stock FROM pantry_items")
            items = [dict(r) for r in cursor.fetchall()]

            for row in items:
                # 1. Remove staples
                if is_staple_ingredient(row["name"], row["display_name"]):
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                # 2. Re-clean name using display_name or name
                cleaned = clean_ingredient_name(row["display_name"]) or clean_ingredient_name(row["name"])
                if not cleaned:
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                clean_norm, clean_disp = cleaned
                if is_staple_ingredient(clean_norm, clean_disp):
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                clean_cat = categorize_ingredient(clean_norm)

                if clean_norm != row["name"]:
                    # Check if another row already exists with clean_norm
                    cursor = conn.execute(
                        "SELECT id, in_stock, display_name FROM pantry_items WHERE name = ? AND id != ?",
                        (clean_norm, row["id"]),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        # Merge stock status
                        if row["in_stock"] == 1 and existing["in_stock"] == 0:
                            conn.execute("UPDATE pantry_items SET in_stock = 1 WHERE id = ?", (existing["id"],))
                        conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                        cleaned_count += 1
                    else:
                        conn.execute(
                            """
                            UPDATE pantry_items 
                            SET name = ?, display_name = ?, category = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE id = ?
                            """,
                            (clean_norm, clean_disp, clean_cat, row["id"]),
                        )
                        cleaned_count += 1
                elif clean_disp != row["display_name"] or clean_cat != row["category"]:
                    conn.execute(
                        """
                        UPDATE pantry_items 
                        SET display_name = ?, category = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                        """,
                        (clean_disp, clean_cat, row["id"]),
                    )
                    cleaned_count += 1

            conn.commit()

        if cleaned_count:
            logger.info(f"Cleaned up / migrated {cleaned_count} pantry items in database.")
        return cleaned_count

    def _invalidate_cache(self):
        self._in_stock_cache = None

    def get_in_stock_set(self) -> Set[str]:
        """Return the cached set of in-stock (or staple) normalized ingredient names."""
        now = time.time()
        if self._in_stock_cache is not None and (now - self._cache_timestamp < 10.0):
            return self._in_stock_cache

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM pantry_items WHERE in_stock = 1 OR is_staple = 1"
            )
            in_stock = {row["name"].lower() for row in cursor.fetchall()}

        # Merge with built-in default staples
        in_stock.update(DEFAULT_STAPLES)

        self._in_stock_cache = in_stock
        self._cache_timestamp = now
        return in_stock

    def get_all_items(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        in_stock: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """List pantry items with optional filtering."""
        query = "SELECT id, name, display_name, category, in_stock, is_staple, updated_at FROM pantry_items WHERE 1=1"
        params: List[Any] = []

        if category:
            query += " AND category = ?"
            params.append(category.lower())
        if in_stock is not None:
            query += " AND in_stock = ?"
            params.append(1 if in_stock else 0)
        if search:
            query += " AND (name LIKE ? OR display_name LIKE ?)"
            term = f"%{search.strip().lower()}%"
            params.extend([term, term])

        query += " ORDER BY category ASC, display_name ASC"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Return counts of total, in_stock, out_of_stock, and staple items."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock,
                    SUM(CASE WHEN in_stock = 0 AND is_staple = 0 THEN 1 ELSE 0 END) as out_of_stock,
                    SUM(CASE WHEN is_staple = 1 THEN 1 ELSE 0 END) as staples
                FROM pantry_items
                """
            )
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "in_stock": row["in_stock"] or 0,
                "out_of_stock": row["out_of_stock"] or 0,
                "staples": row["staples"] or 0,
            }

    def toggle_item(
        self,
        item_id: Optional[int] = None,
        name: Optional[str] = None,
        in_stock: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Toggle or explicitly set the stock status of an item."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            if item_id:
                cursor = conn.execute(
                    "SELECT id, in_stock FROM pantry_items WHERE id = ?", (item_id,)
                )
            elif name:
                norm_name = normalize_ingredient_name(name)
                cursor = conn.execute(
                    "SELECT id, in_stock FROM pantry_items WHERE name = ?", (norm_name,)
                )
            else:
                return None

            row = cursor.fetchone()
            if not row:
                return None

            new_status = (
                (1 if in_stock else 0)
                if in_stock is not None
                else (0 if row["in_stock"] == 1 else 1)
            )

            conn.execute(
                """
                UPDATE pantry_items 
                SET in_stock = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (new_status, row["id"]),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT id, name, display_name, category, in_stock, is_staple FROM pantry_items WHERE id = ?",
                (row["id"],),
            )
            return dict(cursor.fetchone())

    def upsert_item(
        self,
        name: str,
        display_name: Optional[str] = None,
        category: Optional[str] = None,
        in_stock: bool = True,
        is_staple: bool = False,
    ) -> Dict[str, Any]:
        """Add or update a pantry item."""
        self._invalidate_cache()
        cleaned = clean_ingredient_name(name)
        if cleaned:
            norm_name, default_display = cleaned
            clean_display = (display_name or default_display).strip()
        else:
            norm_name = normalize_ingredient_name(name)
            clean_display = (display_name or name).strip().title()

        if not norm_name:
            norm_name = name.strip().lower()

        cat = category or categorize_ingredient(norm_name)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO pantry_items (name, display_name, category, in_stock, is_staple, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    display_name = excluded.display_name,
                    category = excluded.category,
                    in_stock = excluded.in_stock,
                    is_staple = excluded.is_staple,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (norm_name, clean_display, cat, 1 if in_stock else 0, 1 if is_staple else 0),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT id, name, display_name, category, in_stock, is_staple FROM pantry_items WHERE name = ?",
                (norm_name,),
            )
            return dict(cursor.fetchone())

    def delete_item(self, item_id: int) -> bool:
        """Delete an item by ID."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM pantry_items WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def seed_from_recipes(
        self, recipes: List[Dict[str, Any]], mark_in_stock: bool = True
    ) -> int:
        """Extract ingredients from recipes, sanitize them, and populate pantry."""
        self.cleanup_existing_items()
        added_count = 0
        self._invalidate_cache()

        for r in recipes:
            raw_ingredients = r.get("recipeIngredient") or r.get("ingredients") or []
            for item in raw_ingredients:
                raw_name = ""
                if isinstance(item, dict):
                    raw_name = (
                        item.get("food", {}).get("name")
                        if isinstance(item.get("food"), dict) and item.get("food", {}).get("name")
                        else (
                            item.get("name")
                            or item.get("display")
                            or item.get("note")
                            or item.get("originalText")
                            or ""
                        )
                    )
                elif isinstance(item, str):
                    raw_name = item

                if not raw_name:
                    continue

                cleaned = clean_ingredient_name(raw_name)
                if not cleaned:
                    continue

                norm, clean_display = cleaned
                if not norm or norm in DEFAULT_STAPLES or is_staple_ingredient(norm, raw_name):
                    continue

                cat = categorize_ingredient(norm)

                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT id, display_name FROM pantry_items WHERE name = ?", (norm,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        conn.execute(
                            """
                            INSERT INTO pantry_items (name, display_name, category, in_stock, is_staple, updated_at)
                            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                            """,
                            (norm, clean_display, cat, 1 if mark_in_stock else 0),
                        )
                        conn.commit()
                        added_count += 1
                    else:
                        # If existing display_name is much messier or longer, upgrade to clean title
                        old_disp = row["display_name"]
                        if len(clean_display) < len(old_disp) and not re.search(r"[\(\)\[\]\/]", clean_display):
                            conn.execute(
                                "UPDATE pantry_items SET display_name = ? WHERE id = ?",
                                (clean_display, row["id"]),
                            )
                            conn.commit()

        logger.info(f"Seeded {added_count} new ingredients into pantry database.")
        return added_count

    def clear_all_items(self) -> int:
        """Clear all pantry items from the database."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM pantry_items")
            conn.commit()
            deleted = cursor.rowcount
        logger.info(f"Cleared {deleted} items from pantry database.")
        return deleted

    def seed_from_foods(
        self, foods: List[Dict[str, Any]], mark_in_stock: bool = True
    ) -> int:
        """Populate pantry from Mealie food database items."""
        added_count = 0
        self._invalidate_cache()

        for item in foods:
            raw_name = ""
            if isinstance(item, dict):
                raw_name = item.get("name") or item.get("display") or item.get("title") or ""
            elif isinstance(item, str):
                raw_name = item

            if not raw_name:
                continue

            cleaned = clean_ingredient_name(raw_name)
            if not cleaned:
                continue

            norm, clean_display = cleaned
            if not norm or norm in DEFAULT_STAPLES or is_staple_ingredient(norm, raw_name):
                continue

            cat = categorize_ingredient(norm)

            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, display_name FROM pantry_items WHERE name = ?", (norm,)
                )
                row = cursor.fetchone()
                if not row:
                    conn.execute(
                        """
                        INSERT INTO pantry_items (name, display_name, category, in_stock, is_staple, updated_at)
                        VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                        """,
                        (norm, clean_display, cat, 1 if mark_in_stock else 0),
                    )
                    conn.commit()
                    added_count += 1
                elif len(clean_display) < len(row["display_name"]):
                    conn.execute(
                        "UPDATE pantry_items SET display_name = ? WHERE id = ?",
                        (clean_display, row["id"]),
                    )
                    conn.commit()

        logger.info(f"Seeded {added_count} new foods into pantry database.")
        return added_count

    def evaluate_recipe(
        self, recipe: Dict[str, Any], in_stock_set: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """Evaluate whether a recipe can be made given current in-stock pantry items.

        Returns:
            Dict containing:
                missing_count: int
                missing_items: List of missing ingredient display strings
                in_stock_items: List of available ingredient display strings
                total_ingredients: int
                is_ready: bool (missing_count <= 1)
        """
        if in_stock_set is None:
            in_stock_set = self.get_in_stock_set()

        raw_ingredients = (
            recipe.get("recipeIngredient") or recipe.get("ingredients") or []
        )

        missing_items: List[str] = []
        in_stock_items: List[str] = []

        for item in raw_ingredients:
            raw_name = ""
            display_name = ""

            if isinstance(item, dict):
                raw_name = (
                    item.get("food", {}).get("name")
                    if isinstance(item.get("food"), dict) and item.get("food", {}).get("name")
                    else (
                        item.get("name")
                        or item.get("note")
                        or item.get("display")
                        or item.get("originalText")
                        or ""
                    )
                )
                display_name = item.get("display") or item.get("name") or raw_name
            elif isinstance(item, str):
                raw_name = item
                display_name = item

            if not raw_name:
                continue

            cleaned = clean_ingredient_name(raw_name)
            if not cleaned:
                # Discard non-ingredient notes or scraper artifacts
                continue

            norm, clean_display = cleaned
            if not norm:
                continue

            # Always treat built-in staples (salt, pepper, water, oil, AP flour, sugar, pan spray) as in stock
            if norm in DEFAULT_STAPLES or is_staple_ingredient(norm, raw_name):
                continue

            # Check if ingredient matches in-stock set
            # 1. Direct match
            has_match = norm in in_stock_set

            # 2. Substring or token match
            if not has_match:
                for stock_item in in_stock_set:
                    if stock_item in norm or norm in stock_item:
                        has_match = True
                        break

            clean_label = clean_display

            if has_match:
                in_stock_items.append(clean_label)
            else:
                missing_items.append(clean_label)

        missing_count = len(missing_items)
        # Deduplicate missing items
        unique_missing = list(dict.fromkeys(missing_items))

        return {
            "missing_count": missing_count,
            "missing_items": unique_missing,
            "in_stock_items": list(dict.fromkeys(in_stock_items)),
            "total_ingredients": missing_count + len(in_stock_items),
            "is_ready": missing_count <= 1,
            "is_full_pantry": missing_count == 0,
        }


pantry_manager = PantryManager()
