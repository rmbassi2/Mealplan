import logging
import random
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.mock_data import MOCK_RECIPES, generate_recipe_svg

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

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def get_dinner_options(self, count: int = 3) -> List[Dict[str, Any]]:
        """Fetch recipe options from Mealie, or fall back to mock recipes if offline/unconfigured."""
        if not self.mock_mode:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/api/recipes?perPage=50",
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
                            selected = random.sample(items, min(count, len(items)))
                            results = []
                            for r in selected:
                                recipe_id = r.get("id") or r.get("slug")
                                results.append(
                                    {
                                        "id": recipe_id,
                                        "name": r.get("name", "Untitled Recipe"),
                                        "slug": r.get("slug", ""),
                                        "description": r.get("description") or "",
                                        "totalTime": format_recipe_time(r),
                                        "imageUrl": f"/api/recipe-image/{recipe_id}",
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

        # Fallback / Mock Mode: Pick random recipes from MOCK_RECIPES
        selected_mocks = random.sample(MOCK_RECIPES, min(count, len(MOCK_RECIPES)))
        return [
            {
                "id": m["id"],
                "name": m["name"],
                "slug": m["slug"],
                "description": m["description"],
                "totalTime": m["totalTime"],
                "imageUrl": f"/api/recipe-image/{m['id']}",
                "category": m.get("category"),
                "is_mock": True,
            }
            for m in selected_mocks
        ]

    async def get_recipe_image(self, recipe_id: str) -> Tuple[bytes, str]:
        """Proxy recipe image from Mealie, or serve generated SVG if unavailable or mock."""
        # Check if recipe is in mock collection
        mock_recipe = next((m for m in MOCK_RECIPES if m["id"] == recipe_id), None)

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
    ) -> Dict[str, Any]:
        """Submit the selected recipe or custom craving to Mealie Mealplanner API."""
        today_str = date.today().isoformat()

        if recipe_id:
            payload: Dict[str, Any] = {
                "date": today_str,
                "entryType": "dinner",
                "recipeId": recipe_id,
                "title": "",
                "text": "",
            }
        elif custom_note:
            payload = {
                "date": today_str,
                "entryType": "dinner",
                "title": custom_note,
                "text": custom_note,
                "recipeId": None,
            }
        else:
            raise ValueError("Either recipe_id or custom_note must be provided")

        if self.mock_mode:
            logger.info(f"[Mock Mode] Submitted dinner choice for {today_str}: {payload}")
            return {
                "status": "success",
                "message": "Meal plan updated (Mock mode)",
                "date": today_str,
                "entry": payload,
            }

        # Try modern Mealie endpoint (/api/households/mealplans) first,
        # then fallback to legacy (/api/groups/mealplans) if needed
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
                        return {
                            "status": "success",
                            "message": "Meal plan updated",
                            "date": today_str,
                        }
                    elif resp.status_code in (404, 405):
                        # Method not allowed or not found on this path, try next endpoint
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

        # If all candidate endpoints failed:
        raise RuntimeError(last_error or "Failed to submit meal plan: no valid endpoint responded.")


mealie_client = MealieClient()
