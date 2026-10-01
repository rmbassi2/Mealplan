import logging
import random
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.mock_data import MOCK_RECIPES, MOCK_SIDES, generate_recipe_svg
from app.pantry import pantry_manager
from app.taxonomy import extract_recipe_taxonomy, select_balanced_recipes, select_side_recipes
from app.url_helper import extract_url_from_text, fetch_recipe_url_info, clean_domain

logger = logging.getLogger("mealie_client")


def format_recipe_time(recipe: Dict[str, Any]) -> str:
    """Format totalTime, prepTime, or performTime into a user-friendly display string."""
    raw_time = (
        recipe.get("totalTime")
        or recipe.get("prepTime")
        or recipe.get("performTime")
    )
    if not raw_time:
        return "30 mins"

    raw_str = str(raw_time).strip()
    if raw_str.startswith("PT"):
        hours = re.search(r"(\d+)H", raw_str)
        mins = re.search(r"(\d+)M", raw_str)
        parts = []
        if hours:
            h = hours.group(1)
            parts.append(f"{h} hr" if h == "1" else f"{h} hrs")
        if mins:
            parts.append(f"{mins.group(1)} mins")
        if parts:
            return " ".join(parts)

    # If it's pure numbers, assume minutes
    if raw_str.isdigit():
        return f"{raw_str} mins"

    return raw_str


class MealieClient:
    def __init__(self):
        self.base_url = settings.mealie_base_url
        self.token = settings.mealie_api_token
        self.mock_mode = settings.mock_mode or not settings.is_configured
        self._cached_today_plan: Optional[Dict[str, Any]] = None
        self._recipe_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def delete_mealplan_entry(self, entry_id: Any) -> bool:
        """Delete a meal plan entry by ID from Mealie."""
        if self.mock_mode or not entry_id:
            return True

        del_endpoints = [
            f"{self.base_url}/api/households/mealplans/{entry_id}",
            f"{self.base_url}/api/groups/mealplans/{entry_id}",
        ]
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            for url in del_endpoints:
                try:
                    resp = await client.delete(url, headers=self.headers)
                    if resp.status_code in (200, 204):
                        logger.info(f"Deleted meal plan entry {entry_id} via {url}")
                        return True
                except Exception as e:
                    logger.debug(f"Error deleting entry {entry_id} at {url}: {e}")
        return False

    async def clear_today_dinner_entries(self, today_str: Optional[str] = None) -> int:
        """Find and remove all existing dinner entries for today from Mealie."""
        self._cached_today_plan = None
        if not today_str:
            today_str = date.today().isoformat()

        if self.mock_mode:
            return 0

        endpoints = [
            f"{self.base_url}/api/households/mealplans?start_date={today_str}&end_date={today_str}&perPage=100",
            f"{self.base_url}/api/groups/mealplans?start_date={today_str}&end_date={today_str}&perPage=100",
        ]
        deleted_count = 0
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            entries_to_delete = []
            for url in endpoints:
                try:
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        for it in items:
                            if str(it.get("date")) == today_str and str(it.get("entryType", "")).lower() == "dinner":
                                if it.get("id"):
                                    entries_to_delete.append(it["id"])
                        if entries_to_delete:
                            break
                except Exception as e:
                    logger.debug(f"Error querying meal plans for clear: {e}")

            for eid in set(entries_to_delete):
                if await self.delete_mealplan_entry(eid):
                    deleted_count += 1

        return deleted_count

    async def reset_today_plan(self) -> int:
        """Reset and remove today's dinner from Mealie and clear cache."""
        self._cached_today_plan = None
        if self.mock_mode:
            return 0
        return await self.clear_today_dinner_entries()

    async def get_today_plan(self) -> Optional[Dict[str, Any]]:
        """Fetch today's already scheduled dinner from Mealie or cache."""
        today_str = date.today().isoformat()

        if self.mock_mode:
            if self._cached_today_plan and self._cached_today_plan.get("date") == today_str:
                return self._cached_today_plan
            return None

        queried_successfully = False
        endpoints = [
            f"{self.base_url}/api/households/mealplans?start_date={today_str}&end_date={today_str}&perPage=100",
            f"{self.base_url}/api/households/mealplans/today",
            f"{self.base_url}/api/groups/mealplans?start_date={today_str}&end_date={today_str}&perPage=100",
            f"{self.base_url}/api/groups/mealplans/today",
        ]
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            for url in endpoints:
                try:
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        queried_successfully = True
                        data = resp.json()
                        items = []
                        if isinstance(data, dict):
                            if "items" in data:
                                items = data["items"]
                            elif "date" in data:
                                items = [data]
                        elif isinstance(data, list):
                            items = data

                        # Find all dinner entries for today
                        dinner_entries = [
                            it for it in items
                            if str(it.get("date")) == today_str and str(it.get("entryType", "")).lower() == "dinner"
                        ]
                        if not dinner_entries and items:
                            dinner_entries = [it for it in items if str(it.get("date")) == today_str]

                        if dinner_entries:
                            # Classify entries into main and side
                            main_entry = None
                            side_entry = None
                            for ent in dinner_entries:
                                t_text = str(ent.get("title") or ent.get("text") or "").lower()
                                rec_c = str(ent.get("recipe", {}).get("recipeCategory") or "").lower()
                                if t_text.startswith("side:") or "side" in rec_c or "side" in t_text:
                                    if not side_entry:
                                        side_entry = ent
                                        continue
                                if not main_entry:
                                    main_entry = ent
                                elif not side_entry:
                                    side_entry = ent

                            if not main_entry and dinner_entries:
                                main_entry = dinner_entries[0]

                            # Parse main entry
                            dish_name = "Tonight's Recipe"
                            total_time = None
                            recipe_slug = None
                            is_custom = False
                            emoji = "🥘"
                            external_url = None
                            source_domain = None

                            if main_entry:
                                recipe_obj = main_entry.get("recipe")
                                title = main_entry.get("title") or main_entry.get("text")
                                recipe_id = main_entry.get("recipeId")

                                if recipe_obj and isinstance(recipe_obj, dict):
                                    dish_name = recipe_obj.get("name", "Tonight's Recipe")
                                    total_time = format_recipe_time(recipe_obj)
                                    recipe_slug = recipe_obj.get("slug")
                                    emoji = "🥘"
                                elif title:
                                    dish_name = title
                                    is_custom = True
                                    note_text = main_entry.get("text") or ""
                                    found_url = extract_url_from_text(note_text) or extract_url_from_text(title)
                                    external_url = found_url
                                    source_domain = clean_domain(found_url) if found_url else None
                                    emoji = "🌐" if external_url else "🍜"
                                elif recipe_id:
                                    dish_name = "Tonight's Dinner"
                                    emoji = "🍽️"
                                    try:
                                        r_res = await client.get(
                                            f"{self.base_url}/api/recipes/{recipe_id}",
                                            headers=self.headers,
                                        )
                                        if r_res.status_code == 200:
                                            rd = r_res.json()
                                            dish_name = rd.get("name", dish_name)
                                            total_time = format_recipe_time(rd)
                                            recipe_slug = rd.get("slug")
                                    except Exception:
                                        pass

                            # Parse side entry (if any)
                            side_name = None
                            side_time = None
                            side_slug = None
                            side_emoji = None
                            side_external_url = None
                            side_source_domain = None
                            side_is_custom = False

                            if side_entry:
                                s_recipe_obj = side_entry.get("recipe")
                                s_title = side_entry.get("title") or side_entry.get("text")
                                s_recipe_id = side_entry.get("recipeId")

                                if s_recipe_obj and isinstance(s_recipe_obj, dict):
                                    side_name = s_recipe_obj.get("name", "Side Dish")
                                    side_time = format_recipe_time(s_recipe_obj)
                                    side_slug = s_recipe_obj.get("slug")
                                    side_emoji = "🥗"
                                elif s_title:
                                    s_text = side_entry.get("text") or ""
                                    s_url = extract_url_from_text(s_text) or extract_url_from_text(s_title)
                                    side_name = re.sub(r"^side:\s*", "", s_title, flags=re.IGNORECASE)
                                    side_is_custom = True
                                    side_external_url = s_url
                                    side_source_domain = clean_domain(s_url) if s_url else None
                                    side_emoji = "🌐" if s_url else "🥗"
                                elif s_recipe_id:
                                    side_name = "Side Dish"
                                    side_emoji = "🥗"
                                    try:
                                        r_res = await client.get(
                                            f"{self.base_url}/api/recipes/{s_recipe_id}",
                                            headers=self.headers,
                                        )
                                        if r_res.status_code == 200:
                                            rd = r_res.json()
                                            side_name = rd.get("name", side_name)
                                            side_time = format_recipe_time(rd)
                                            side_slug = rd.get("slug")
                                    except Exception:
                                        pass

                            plan = {
                                "date": today_str,
                                "dish_name": dish_name,
                                "total_time": total_time,
                                "recipe_slug": recipe_slug,
                                "is_custom": is_custom,
                                "external_url": external_url,
                                "source_domain": source_domain,
                                "emoji": emoji,
                                "side_name": side_name,
                                "side_time": side_time,
                                "side_slug": side_slug,
                                "side_emoji": side_emoji,
                                "side_external_url": side_external_url,
                                "side_source_domain": side_source_domain,
                                "side_is_custom": side_is_custom,
                            }
                            self._cached_today_plan = plan
                            return plan
                except Exception as e:
                    logger.debug(f"Error checking existing meal plan at {url}: {e}")
                    continue

        if queried_successfully:
            # Mealie explicitly confirmed no dinner planned for today
            self._cached_today_plan = None
            return None

        # Fallback to cache only if Mealie was completely unreachable
        if self._cached_today_plan and self._cached_today_plan.get("date") == today_str:
            return self._cached_today_plan
        return None

    async def add_to_shopping_list(self, item_name: str, note: Optional[str] = None) -> Dict[str, Any]:
        """Add an item (e.g. missing ingredient) to Mealie's shopping list."""
        if self.mock_mode:
            logger.info(f"[Mock Mode] Added '{item_name}' to shopping list.")
            return {
                "status": "success",
                "message": f"Added '{item_name}' to shopping list (Mock mode)",
                "item_name": item_name,
            }

        endpoints = [
            f"{self.base_url}/api/households/shopping/items",
            f"{self.base_url}/api/groups/shopping/items",
        ]
        payload = {
            "note": f"{item_name}" + (f" ({note})" if note else ""),
            "checked": False,
        }
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            for url in endpoints:
                try:
                    resp = await client.post(url, headers=self.headers, json=payload)
                    if resp.status_code in (200, 201):
                        logger.info(f"Successfully added '{item_name}' to Mealie shopping list via {url}")
                        return {
                            "status": "success",
                            "message": f"Added '{item_name}' to shopping list",
                            "item": resp.json() if resp.text else None,
                        }
                except Exception as e:
                    logger.debug(f"Error posting to shopping list at {url}: {e}")

        return {
            "status": "error",
            "message": f"Could not add '{item_name}' to Mealie shopping list",
        }

    async def get_dinner_options(
        self,
        count: int = 3,
        mood: Optional[str] = None,
        protein: Optional[str] = None,
        tool: Optional[str] = None,
        cuisine: Optional[str] = None,
        pantry_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Fetch recipe options with taxonomy-aware balanced selection, pantry status, and badges."""
        in_stock_set = pantry_manager.get_in_stock_set()

        if not self.mock_mode:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/api/recipes?perPage=100",
                        headers=self.headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = (
                            data.get("items", [])
                            if isinstance(data, dict)
                            else data
                            if isinstance(data, list)
                            else []
                        )

                        if items:
                            # Auto-seed pantry if it is currently empty
                            if pantry_manager.get_stats()["total"] == 0:
                                pantry_manager.seed_from_recipes(items)
                                in_stock_set = pantry_manager.get_in_stock_set()

                            # Evaluate pantry status for each recipe
                            for r in items:
                                r["_pantry"] = pantry_manager.evaluate_recipe(r, in_stock_set)

                            candidate_items = items
                            if pantry_only or mood in ("pantry", "pantry-ready"):
                                ready_pool = [r for r in items if r["_pantry"]["is_ready"]]
                                if ready_pool:
                                    candidate_items = ready_pool

                            selected = select_balanced_recipes(
                                candidate_items,
                                count=count,
                                mood=mood,
                                protein=protein,
                                tool=tool,
                                cuisine=cuisine,
                            )
                            results = []
                            for r in selected:
                                tax = r.get("_taxonomy") or extract_recipe_taxonomy(r)
                                recipe_id = r.get("id") or r.get("slug")
                                # Derive category label
                                cat_label = "Dinner"
                                raw_cats = r.get("recipeCategory") or r.get("categories") or []
                                if raw_cats and isinstance(raw_cats, list):
                                    first_c = raw_cats[0]
                                    cat_label = first_c.get("name") if isinstance(first_c, dict) else str(first_c)

                                results.append(
                                    {
                                        "id": recipe_id,
                                        "name": r.get("name", "Untitled Recipe"),
                                        "slug": r.get("slug", ""),
                                        "description": r.get("description") or "",
                                        "totalTime": format_recipe_time(r),
                                        "imageUrl": f"/api/recipe-image/{recipe_id}",
                                        "category": cat_label,
                                        "badges": tax.get("badges", []),
                                        "tags": list(tax.get("tags", set())),
                                        "tools": list(tax.get("tools", set())),
                                        "pantry": r.get("_pantry", {
                                            "is_ready": True,
                                            "missing_count": 0,
                                            "missing_items": [],
                                            "in_stock_items": [],
                                            "is_full_pantry": True,
                                        }),
                                        "is_mock": False,
                                    }
                                )
                            return results
                        else:
                            logger.warning("Mealie returned 0 recipes, falling back to mock options.")
                    else:
                        logger.warning(
                            f"Mealie API returned status {resp.status_code}: {resp.text}, using mock options."
                        )
            except Exception as e:
                logger.warning(f"Failed to connect to Mealie ({e}), falling back to mock options.")

        # Fallback / Mock Mode: Auto-seed pantry if empty and evaluate MOCK_RECIPES
        if pantry_manager.get_stats()["total"] == 0:
            pantry_manager.seed_from_recipes(MOCK_RECIPES)
            in_stock_set = pantry_manager.get_in_stock_set()

        for m in MOCK_RECIPES:
            m["_pantry"] = pantry_manager.evaluate_recipe(m, in_stock_set)

        mock_candidates = MOCK_RECIPES
        if pantry_only or mood in ("pantry", "pantry-ready"):
            ready_mocks = [m for m in MOCK_RECIPES if m["_pantry"]["is_ready"]]
            if ready_mocks:
                mock_candidates = ready_mocks

        selected_mocks = select_balanced_recipes(
            mock_candidates,
            count=count,
            mood=mood,
            protein=protein,
            tool=tool,
            cuisine=cuisine,
        )
        results = []
        for m in selected_mocks:
            tax = m.get("_taxonomy") or extract_recipe_taxonomy(m)
            results.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "slug": m["slug"],
                    "description": m["description"],
                    "totalTime": m["totalTime"],
                    "imageUrl": f"/api/recipe-image/{m['id']}",
                    "category": m.get("category", "Dinner"),
                    "badges": tax.get("badges", []),
                    "tags": list(tax.get("tags", set())),
                    "tools": list(tax.get("tools", set())),
                    "emoji": m.get("emoji", "🥘"),
                    "pantry": m.get("_pantry", {
                        "is_ready": True,
                        "missing_count": 0,
                        "missing_items": [],
                        "in_stock_items": [],
                        "is_full_pantry": True,
                    }),
                    "is_mock": True,
                }
            )
        return results

    async def get_side_options(self, count: int = 3) -> List[Dict[str, Any]]:
        """Fetch side dish options from Mealie, falling back to curated mock sides if needed."""
        if not self.mock_mode:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/api/recipes?perPage=100",
                        headers=self.headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = (
                            data.get("items", [])
                            if isinstance(data, dict)
                            else data
                            if isinstance(data, list)
                            else []
                        )
                        selected = select_side_recipes(items, count=count)
                        results = []
                        for r in selected:
                            recipe_id = r.get("id") or r.get("slug")
                            tax = r.get("_taxonomy") or extract_recipe_taxonomy(r)
                            results.append(
                                {
                                    "id": recipe_id,
                                    "name": r.get("name", "Side Dish"),
                                    "slug": r.get("slug", ""),
                                    "description": r.get("description") or "A tasty side to complement dinner.",
                                    "totalTime": format_recipe_time(r),
                                    "imageUrl": f"/api/recipe-image/{recipe_id}",
                                    "category": "Side Dish",
                                    "badges": tax.get("badges", []),
                                    "emoji": "🥗",
                                    "is_mock": False,
                                }
                            )
                        if len(results) < count:
                            needed = count - len(results)
                            for m in random.sample(MOCK_SIDES, min(needed, len(MOCK_SIDES))):
                                results.append(
                                    {
                                        "id": m["id"],
                                        "name": m["name"],
                                        "slug": m["slug"],
                                        "description": m["description"],
                                        "totalTime": m["totalTime"],
                                        "imageUrl": f"/api/recipe-image/{m['id']}",
                                        "category": m.get("category", "Side Dish"),
                                        "badges": [{"icon": "✨", "label": "Pantry Fav", "type": "vibe"}],
                                        "emoji": m.get("emoji", "🥗"),
                                        "is_mock": True,
                                    }
                                )
                        return results[:count]
            except Exception as e:
                logger.warning(f"Error querying Mealie for sides, using fallback: {e}")

        # In mock mode or fallback
        sample_sides = random.sample(MOCK_SIDES, min(count, len(MOCK_SIDES)))
        return [
            {
                "id": m["id"],
                "name": m["name"],
                "slug": m["slug"],
                "description": m["description"],
                "totalTime": m["totalTime"],
                "imageUrl": f"/api/recipe-image/{m['id']}",
                "category": m.get("category", "Side Dish"),
                "badges": [{"icon": "✨", "label": "Pantry Fav", "type": "vibe"}],
                "emoji": m.get("emoji", "🥗"),
                "is_mock": True,
            }
            for m in sample_sides
        ]

    async def get_recipe_image(self, recipe_id: str) -> Tuple[bytes, str]:
        """Proxy recipe image from Mealie, or serve generated SVG if unavailable or mock."""
        # Check if recipe is in mock collection
        mock_recipe = next((m for m in MOCK_RECIPES if m["id"] == recipe_id), None)
        if not mock_recipe:
            mock_recipe = next((m for m in MOCK_SIDES if m["id"] == recipe_id), None)

        if not self.mock_mode and not mock_recipe:
            try:
                # Try original.webp first, then min-original.webp
                endpoints = [
                    f"{self.base_url}/api/media/recipes/{recipe_id}/images/original.webp",
                    f"{self.base_url}/api/media/recipes/{recipe_id}/images/min-original.webp",
                ]
                async with httpx.AsyncClient(timeout=6.0) as client:
                    for url in endpoints:
                        resp = await client.get(url, headers=self.headers)
                        if resp.status_code == 200:
                            content_type = resp.headers.get("content-type", "image/webp")
                            return resp.content, content_type
            except Exception as e:
                logger.warning(f"Error fetching image for recipe {recipe_id} from Mealie: {e}")

        # Return mock SVG
        if mock_recipe:
            svg = generate_recipe_svg(
                title=mock_recipe["name"],
                emoji=mock_recipe.get("emoji", "🍽️"),
                c1=mock_recipe.get("gradient", ("#f59e0b", "#b45309"))[0],
                c2=mock_recipe.get("gradient", ("#f59e0b", "#b45309"))[1],
            )
        else:
            svg = generate_recipe_svg(title="Delicious Dinner", emoji="🥘")

        return svg.encode("utf-8"), "image/svg+xml"

    async def submit_choice(
        self,
        recipe_id: Optional[str] = None,
        custom_note: Optional[str] = None,
        side_recipe_id: Optional[str] = None,
        side_custom_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit the selected recipe or custom craving, plus optional side dish to Mealie."""
        today_str = date.today().isoformat()
        dish_name = "Dinner"
        total_time = None
        recipe_slug = None
        is_custom = False

        external_url = None
        source_domain = None

        if recipe_id:
            # Check mock recipes first
            mock_recipe = next((m for m in MOCK_RECIPES if m["id"] == recipe_id), None)
            if mock_recipe:
                dish_name = mock_recipe["name"]
                total_time = mock_recipe.get("totalTime")
                recipe_slug = mock_recipe.get("slug")
            elif not self.mock_mode:
                try:
                    async with httpx.AsyncClient(timeout=4.0) as client:
                        r_resp = await client.get(
                            f"{self.base_url}/api/recipes/{recipe_id}",
                            headers=self.headers,
                        )
                        if r_resp.status_code == 200:
                            r_data = r_resp.json()
                            dish_name = r_data.get("name", "Selected Recipe")
                            total_time = format_recipe_time(r_data)
                            recipe_slug = r_data.get("slug")
                except Exception as e:
                    logger.debug(f"Could not retrieve recipe metadata for {recipe_id}: {e}")

            payload: Dict[str, Any] = {
                "date": today_str,
                "entryType": "dinner",
                "recipeId": recipe_id,
                "title": "",
                "text": "",
            }
        elif custom_note:
            found_url = extract_url_from_text(custom_note)
            if found_url:
                external_url = found_url
                source_domain = clean_domain(found_url)
                # Fetch clean title from webpage (fast 3-4s timeout)
                page_title, _ = await fetch_recipe_url_info(found_url)

                text_without_url = custom_note.replace(found_url, "").strip(" -:–—\t\r\n")
                dish_name = page_title or text_without_url or f"Recipe from {source_domain}"
                is_custom = True

                note_lines = []
                if text_without_url:
                    note_lines.append(f"Note: {text_without_url}")
                note_lines.append(f"Recipe Link: {found_url}")
                note_lines.append(f"Source: {source_domain}")

                payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "title": dish_name,
                    "text": "\n\n".join(note_lines),
                    "recipeId": None,
                }
            else:
                dish_name = custom_note
                is_custom = True
                payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "title": custom_note,
                    "text": custom_note,
                    "recipeId": None,
                }
        else:
            raise ValueError("Either recipe_id or custom_note must be provided")

        # Parse side dish (if any)
        side_name = None
        side_time = None
        side_slug = None
        side_is_custom = False
        side_external_url = None
        side_source_domain = None
        side_emoji = None
        side_payload = None

        if side_recipe_id:
            mock_side = next((m for m in MOCK_SIDES if m["id"] == side_recipe_id), None)
            if mock_side:
                side_name = mock_side["name"]
                side_time = mock_side.get("totalTime")
                side_slug = mock_side.get("slug")
                side_emoji = mock_side.get("emoji", "🥗")
                side_payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "title": f"Side: {side_name}",
                    "text": f"Side: {side_name}",
                    "recipeId": None,
                }
            elif not self.mock_mode:
                try:
                    async with httpx.AsyncClient(timeout=4.0) as client:
                        s_resp = await client.get(
                            f"{self.base_url}/api/recipes/{side_recipe_id}",
                            headers=self.headers,
                        )
                        if s_resp.status_code == 200:
                            s_data = s_resp.json()
                            side_name = s_data.get("name", "Selected Side")
                            side_time = format_recipe_time(s_data)
                            side_slug = s_data.get("slug")
                            side_emoji = "🥗"
                except Exception as e:
                    logger.debug(f"Could not retrieve side metadata for {side_recipe_id}: {e}")

                side_payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "recipeId": side_recipe_id,
                    "title": "",
                    "text": "",
                }
        elif side_custom_note:
            side_is_custom = True
            found_side_url = extract_url_from_text(side_custom_note)
            if found_side_url:
                side_external_url = found_side_url
                side_source_domain = clean_domain(found_side_url)
                page_title, _ = await fetch_recipe_url_info(found_side_url)
                text_without_url = side_custom_note.replace(found_side_url, "").strip(" -:–—\t\r\n")
                side_name = page_title or text_without_url or f"Side from {side_source_domain}"
                side_emoji = "🌐"
                side_payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "title": f"Side: {side_name}",
                    "text": f"Side Recipe Link: {found_side_url}\nSource: {side_source_domain}",
                    "recipeId": None,
                }
            else:
                side_name = side_custom_note
                side_emoji = "🥗"
                side_payload = {
                    "date": today_str,
                    "entryType": "dinner",
                    "title": f"Side: {side_custom_note}",
                    "text": f"Side: {side_custom_note}",
                    "recipeId": None,
                }

        emoji = "🌐" if external_url else ("🍜" if is_custom else "🥘")
        plan = {
            "date": today_str,
            "dish_name": dish_name,
            "total_time": total_time,
            "recipe_slug": recipe_slug,
            "is_custom": is_custom,
            "external_url": external_url,
            "source_domain": source_domain,
            "emoji": emoji,
            "side_name": side_name,
            "side_time": side_time,
            "side_slug": side_slug,
            "side_emoji": side_emoji,
            "side_external_url": side_external_url,
            "side_source_domain": side_source_domain,
            "side_is_custom": side_is_custom,
        }

        if self.mock_mode:
            logger.info(f"[Mock Mode] Submitted dinner choice for {today_str}: {payload}, side: {side_payload}")
            self._cached_today_plan = plan
            return {
                "status": "success",
                "message": "Meal plan updated (Mock mode)",
                **plan,
                "entry": payload,
                "side_entry": side_payload,
            }

        # Clear any existing dinner entries for today in Mealie so exactly tonight's meal and side exist
        try:
            await self.clear_today_dinner_entries(today_str)
        except Exception as e:
            logger.warning(f"Could not clear prior dinner entries for {today_str}: {e}")

        endpoints = [
            f"{self.base_url}/api/households/mealplans",
            f"{self.base_url}/api/households/mealplans/",
            f"{self.base_url}/api/groups/mealplans",
            f"{self.base_url}/api/groups/mealplans/",
        ]

        last_error = ""
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for url in endpoints:
                try:
                    resp = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code in (200, 201):
                        logger.info(f"Successfully posted dinner choice to Mealie ({url}): {resp.text}")

                        # Also submit side dish if selected
                        if side_payload:
                            try:
                                await client.post(
                                    url,
                                    headers={
                                        "Authorization": f"Bearer {self.token}",
                                        "Content-Type": "application/json",
                                        "Accept": "application/json",
                                    },
                                    json=side_payload,
                                )
                                logger.info(f"Successfully posted side dish to Mealie ({url})")
                            except Exception as side_err:
                                logger.warning(f"Could not post side dish entry: {side_err}")

                        self._cached_today_plan = plan
                        return {
                            "status": "success",
                            "message": "Meal plan updated",
                            **plan,
                        }
                    elif resp.status_code in (404, 405):
                        last_error = f"Mealie API error ({resp.status_code}) on {url}: {resp.text}"
                        continue
                    else:
                        logger.error(f"Mealie error ({resp.status_code}) on {url}: {resp.text}")
                        raise RuntimeError(f"Mealie API error ({resp.status_code}): {resp.text}")
                except RuntimeError:
                    raise
                except Exception as e:
                    last_error = str(e)
                    continue

        raise RuntimeError(last_error or "Failed to submit meal plan: no valid endpoint responded.")


mealie_client = MealieClient()
