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
    r"\b(cups?|tbsp|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|kg|"
    r"ml|liters?|cloves?|slices?|pinch(es)?|dash(es)?|cans?|jars?|packages?|pkgs?|"
    r"heads?|bunches?|stalks?|pieces?)\b",
    re.IGNORECASE,
)

PREP_WORDS = re.compile(
    r"\b(organic|diced|chopped|minced|sliced|crushed|grated|shredded|melted|softened|"
    r"warm|cold|fresh|freshly|dried|ground|boneless|skinless|cooked|uncooked|"
    r"to taste|divided|optional|room temperature)\b",
    re.IGNORECASE,
)


def normalize_ingredient_name(raw: str) -> str:
    """Clean and normalize an ingredient name for fuzzy matching."""
    if not raw:
        return ""
    text = raw.lower().strip()
    # Remove measurement expressions and prep words
    text = MEASUREMENT_WORDS.sub(" ", text)
    text = PREP_WORDS.sub(" ", text)
    text = UNIT_WORDS.sub(" ", text)
    # Remove standalone numbers or fractions
    text = re.sub(r"\b\d+([./]\d+)?\b", " ", text)
    # Remove punctuation & extra whitespace
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def categorize_ingredient(name: str) -> str:
    """Smart heuristic categorization for pantry items."""
    n = name.lower()
    if any(k in n for k in ["chicken", "beef", "pork", "steak", "turkey", "lamb", "bacon", "salmon", "shrimp", "fish", "tuna", "patty", "patties"]):
        return "protein"
    if any(k in n for k in ["milk", "cream", "cheese", "butter", "yogurt", "mozzarella", "parmesan", "cheddar"]):
        return "dairy"
    if any(k in n for k in ["tomato", "onion", "garlic", "spinach", "lettuce", "cilantro", "basil", "parsley", "lemon", "lime", "potato", "carrot", "broccoli", "zucchini", "cucumber", "cabbage", "sprouts", "sage", "rosemary", "chile", "peppers"]):
        return "produce"
    if any(k in n for k in ["rice", "noodle", "pasta", "bread", "bun", "dough", "tortilla", "spaghetti", "orzo"]):
        return "grains & bakery"
    if any(k in n for k in ["oil", "vinegar", "soy sauce", "hoisin", "sauce", "peanut butter", "honey", "broth", "miso"]):
        return "sauces & condiments"
    if any(k in n for k in ["paprika", "cumin", "oregano", "sesame", "cinnamon", "spice", "nutmeg"]):
        return "spices & herbs"
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
        """Initialize pantry SQLite schema."""
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
        norm_name = normalize_ingredient_name(name)
        if not norm_name:
            norm_name = name.strip().lower()

        clean_display = (display_name or name).strip().title()
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
        """Extract ingredients from recipes and populate pantry if missing."""
        added_count = 0
        self._invalidate_cache()

        for r in recipes:
            raw_ingredients = r.get("recipeIngredient") or r.get("ingredients") or []
            for item in raw_ingredients:
                raw_name = ""
                if isinstance(item, dict):
                    raw_name = (
                        item.get("food", {}).get("name")
                        if isinstance(item.get("food"), dict)
                        else (
                            item.get("name")
                            or item.get("display")
                            or item.get("note")
                            or ""
                        )
                    )
                elif isinstance(item, str):
                    raw_name = item

                if not raw_name:
                    continue

                norm = normalize_ingredient_name(raw_name)
                if not norm or norm in DEFAULT_STAPLES:
                    continue

                clean_display = raw_name.strip()
                # Clean up display if it has quantity leading
                clean_display = MEASUREMENT_WORDS.sub("", clean_display).strip().title()
                if not clean_display:
                    clean_display = norm.title()

                cat = categorize_ingredient(norm)

                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT id FROM pantry_items WHERE name = ?", (norm,)
                    )
                    if not cursor.fetchone():
                        conn.execute(
                            """
                            INSERT INTO pantry_items (name, display_name, category, in_stock, is_staple, updated_at)
                            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                            """,
                            (norm, clean_display, cat, 1 if mark_in_stock else 0),
                        )
                        conn.commit()
                        added_count += 1

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

            norm = normalize_ingredient_name(raw_name)
            if not norm or norm in DEFAULT_STAPLES:
                continue

            clean_display = raw_name.strip()
            clean_display = MEASUREMENT_WORDS.sub("", clean_display).strip().title()
            if not clean_display:
                clean_display = norm.title()

            cat = categorize_ingredient(norm)

            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id FROM pantry_items WHERE name = ?", (norm,)
                )
                if not cursor.fetchone():
                    conn.execute(
                        """
                        INSERT INTO pantry_items (name, display_name, category, in_stock, is_staple, updated_at)
                        VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                        """,
                        (norm, clean_display, cat, 1 if mark_in_stock else 0),
                    )
                    conn.commit()
                    added_count += 1

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
                    if isinstance(item.get("food"), dict)
                    else (
                        item.get("name")
                        or item.get("note")
                        or item.get("display")
                        or ""
                    )
                )
                display_name = item.get("display") or item.get("name") or raw_name
            elif isinstance(item, str):
                raw_name = item
                display_name = item

            if not raw_name:
                continue

            norm = normalize_ingredient_name(raw_name)
            if not norm:
                continue

            # Always treat built-in staples (salt, pepper, water, oil) as in stock
            if norm in DEFAULT_STAPLES or any(s in norm for s in ["salt", "water", "black pepper"]):
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

            clean_label = display_name or norm.title()
            # Tidy display label: remove leading numbers if raw
            clean_label = re.sub(r"^\s*[\d./-]+\s*(cups?|tbsp|tsp|lbs?|oz|g)?\s*", "", clean_label).strip().title()
            if not clean_label:
                clean_label = norm.title()

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
