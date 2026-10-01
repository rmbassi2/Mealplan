import logging
from datetime import date
from typing import Optional
from fastapi import FastAPI, HTTPException, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator

from app.config import settings
from app.mealie_client import mealie_client
from app.notifier import notifier
from app.pantry import pantry_manager
from app.url_helper import fetch_recipe_url_info, clean_domain

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dinner_decider")

app = FastAPI(
    title="Dinner Decider",
    description="A lightweight, mobile-first dinner voting web app integrated with Mealie and smart pantry inventory.",
    version="1.1.0",
)

# Enable CORS for convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DinnerChoice(BaseModel):
    recipe_id: Optional[str] = None
    custom_note: Optional[str] = None
    side_recipe_id: Optional[str] = None
    side_custom_note: Optional[str] = None

    @model_validator(mode="after")
    def validate_choice(self):
        has_recipe = bool(self.recipe_id and self.recipe_id.strip())
        has_custom = bool(self.custom_note and self.custom_note.strip())
        if not has_recipe and not has_custom:
            raise ValueError("Either recipe_id or custom_note must be provided.")
        return self


class PantryToggleRequest(BaseModel):
    item_id: Optional[int] = None
    name: Optional[str] = None
    in_stock: Optional[bool] = None


class PantryItemCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    category: Optional[str] = "pantry"
    in_stock: bool = True
    is_staple: bool = False


class ShoppingListAddRequest(BaseModel):
    item_name: str
    recipe_id: Optional[str] = None
    note: Optional[str] = None


@app.get("/health")
async def health_check():
    """Healthcheck endpoint for container and deployment monitors."""
    stats = pantry_manager.get_stats()
    return {
        "status": "healthy",
        "mock_mode": mealie_client.mock_mode,
        "mealie_configured": settings.is_configured,
        "base_url": settings.mealie_base_url or "(none)",
        "ntfy_configured": settings.is_ntfy_configured,
        "ntfy_topic": settings.ntfy_topic or "(none)",
        "pantry_total": stats["total"],
        "pantry_in_stock": stats["in_stock"],
    }


@app.get("/api/mealie/status")
async def get_mealie_status():
    """Diagnostic endpoint checking live connection to Mealie and count of recipes/foods."""
    status = await mealie_client.check_connection()
    stats = pantry_manager.get_stats()
    return {
        **status,
        "pantry": {
            "total_items": stats["total"],
            "in_stock": stats["in_stock"],
            "out_of_stock": stats["out_of_stock"],
        },
    }


@app.get("/api/today")
async def get_today_dinner():
    """Check if dinner has already been selected for today."""
    try:
        plan = await mealie_client.get_today_plan()
        today_str = date.today().isoformat()
        if plan and plan.get("date") == today_str:
            recipe_slug = plan.get("recipe_slug")
            group = settings.mealie_group_slug or "home"
            link = None
            if settings.mealie_base_url:
                if recipe_slug:
                    link = f"{settings.mealie_base_url}/g/{group}/r/{recipe_slug}"
                else:
                    link = f"{settings.mealie_base_url}/g/{group}/planner"

            side_slug = plan.get("side_slug")
            side_link = None
            if settings.mealie_base_url and plan.get("side_name"):
                if side_slug:
                    side_link = f"{settings.mealie_base_url}/g/{group}/r/{side_slug}"
                else:
                    side_link = f"{settings.mealie_base_url}/g/{group}/planner"

            return {
                "has_plan": True,
                "plan": {
                    **plan,
                    "mealie_url": link,
                    "side_mealie_url": side_link,
                },
            }
        return {"has_plan": False, "plan": None}
    except Exception as e:
        logger.error(f"Error checking today's dinner plan: {e}")
        return {"has_plan": False, "plan": None}


@app.post("/api/cleanup-today")
async def cleanup_today_dinner():
    """Clean up duplicate dinner entries for today in Mealie, keeping only the single latest meal."""
    try:
        plan = await mealie_client.get_today_plan()
        return {
            "status": "success",
            "message": "Cleaned up duplicate dinner entries for today in Mealie",
            "active_plan": plan,
        }
    except Exception as e:
        logger.error(f"Error during dinner cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset-today")
async def reset_today_dinner():
    """Reset today's meal plan in Mealie and clear local cached plan so voting is reopened."""
    try:
        deleted = await mealie_client.reset_today_plan()
        return {
            "status": "success",
            "message": "Today's meal plan has been reset",
            "deleted_count": deleted,
        }
    except Exception as e:
        logger.error(f"Error resetting today's dinner: {e}")
        return {"status": "success", "deleted_count": 0}



@app.get("/api/taxonomy")
async def get_taxonomy_filters():
    """Return available taxonomy filter options and curated mood presets for the frontend."""
    return {
        "moods": [
            {"id": "surprise", "label": "Surprise Me", "icon": "✨"},
            {"id": "pantry", "label": "Pantry Ready", "icon": "🧺"},
            {"id": "quick", "label": "Quick (<30m)", "icon": "⚡"},
            {"id": "comfort", "label": "Comfort Food", "icon": "🧀"},
            {"id": "skillet", "label": "Skillet", "icon": "🍳"},
            {"id": "one-pot", "label": "One-Pot", "icon": "🍲"},
            {"id": "chicken", "label": "Chicken", "icon": "🍗"},
            {"id": "beef", "label": "Beef", "icon": "🥩"},
            {"id": "pork", "label": "Pork", "icon": "🥓"},
            {"id": "pasta", "label": "Pasta", "icon": "🍝"},
            {"id": "seafood", "label": "Seafood", "icon": "🐟"},
            {"id": "fresh", "label": "Light & Fresh", "icon": "🥗"},
            {"id": "sheet-pan", "label": "Sheet Pan", "icon": "🥘"},
            {"id": "grill", "label": "Grill / BBQ", "icon": "🔥"},
            {"id": "asian", "label": "Asian", "icon": "🥢"},
            {"id": "italian", "label": "Italian", "icon": "🇮🇹"},
            {"id": "mexican", "label": "Mexican", "icon": "🌮"},
            {"id": "vegetarian", "label": "Vegetarian", "icon": "🥑"},
        ],
    }


@app.get("/api/options")
async def get_dinner_options(
    mood: Optional[str] = None,
    protein: Optional[str] = None,
    tool: Optional[str] = None,
    cuisine: Optional[str] = None,
    pantry_only: Optional[bool] = False,
):
    """Fetch 3 balanced dinner recipe options from Mealie, with optional mood, protein, tool, cuisine, or pantry filtering."""
    try:
        options = await mealie_client.get_dinner_options(
            count=3,
            mood=mood,
            protein=protein,
            tool=tool,
            cuisine=cuisine,
            pantry_only=bool(pantry_only or (mood in ("pantry", "pantry-ready"))),
        )
        return {
            "options": options,
            "count": len(options),
            "active_filters": {
                "mood": mood,
                "protein": protein,
                "tool": tool,
                "cuisine": cuisine,
                "pantry_only": pantry_only,
            },
            "is_mock": mealie_client.mock_mode or any(o.get("is_mock") for o in options),
        }
    except Exception as e:
        logger.error(f"Error fetching dinner options: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dinner options")


@app.get("/api/pantry")
async def get_pantry(
    category: Optional[str] = None,
    search: Optional[str] = None,
    in_stock: Optional[bool] = None,
):
    """List pantry inventory items with statistics."""
    try:
        # If pantry has zero items yet, auto-seed with Mealie foods or mock recipes
        stats = pantry_manager.get_stats()
        if stats["total"] == 0:
            if mealie_client.mock_mode:
                from app.mock_data import MOCK_RECIPES
                pantry_manager.seed_from_recipes(MOCK_RECIPES, mark_in_stock=True)
            else:
                foods = await mealie_client.get_all_foods()
                if foods:
                    pantry_manager.seed_from_foods(foods, mark_in_stock=True)
                else:
                    from app.mock_data import MOCK_RECIPES
                    pantry_manager.seed_from_recipes(MOCK_RECIPES, mark_in_stock=True)

        items = pantry_manager.get_all_items(category=category, search=search, in_stock=in_stock)
        return {
            "items": items,
            "stats": pantry_manager.get_stats(),
        }
    except Exception as e:
        logger.error(f"Error querying pantry: {e}")
        raise HTTPException(status_code=500, detail="Failed to load pantry inventory")


@app.post("/api/pantry/toggle")
async def toggle_pantry_item(req: PantryToggleRequest):
    """Toggle in_stock availability for a single pantry item."""
    try:
        updated = pantry_manager.toggle_item(item_id=req.item_id, name=req.name, in_stock=req.in_stock)
        if not updated:
            raise HTTPException(status_code=404, detail="Pantry item not found")
        return {
            "status": "success",
            "item": updated,
            "stats": pantry_manager.get_stats(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling pantry item: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle pantry item")


@app.post("/api/pantry/item")
async def upsert_pantry_item(item: PantryItemCreate):
    """Add or update a custom item in the pantry inventory."""
    try:
        saved = pantry_manager.upsert_item(
            name=item.name,
            display_name=item.display_name,
            category=item.category,
            in_stock=item.in_stock,
            is_staple=item.is_staple,
        )
        return {
            "status": "success",
            "item": saved,
            "stats": pantry_manager.get_stats(),
        }
    except Exception as e:
        logger.error(f"Error saving pantry item: {e}")
        raise HTTPException(status_code=500, detail="Failed to save pantry item")


@app.delete("/api/pantry/item/{item_id}")
async def delete_pantry_item(item_id: int):
    """Remove an item from the pantry inventory."""
    try:
        success = pantry_manager.delete_item(item_id)
        if not success:
            raise HTTPException(status_code=404, detail="Item not found")
        return {
            "status": "success",
            "stats": pantry_manager.get_stats(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pantry item: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete pantry item")


@app.post("/api/pantry/sync")
async def sync_pantry_from_recipes(clear_existing: bool = False):
    """Auto-discover and populate pantry ingredients from all recipes and Mealie food database."""
    try:
        if clear_existing:
            pantry_manager.clear_all_items()

        added = 0
        if not mealie_client.mock_mode:
            # 1. Primary: Seed from Mealie's food library
            foods = await mealie_client.get_all_foods()
            if foods:
                added += pantry_manager.seed_from_foods(foods, mark_in_stock=True)

            # 2. Secondary: Fetch recipes and parse ingredients
            try:
                import httpx
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(
                        f"{mealie_client.base_url}/api/recipes?perPage=100",
                        headers=mealie_client.headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = (
                            data.get("items", [])
                            if isinstance(data, dict)
                            else (data if isinstance(data, list) else [])
                        )
                        if items:
                            await mealie_client.enrich_recipe_ingredients(items, max_fetch=30)
                            added += pantry_manager.seed_from_recipes(items, mark_in_stock=True)
            except Exception as e:
                logger.warning(f"Could not fetch Mealie recipes for pantry sync: {e}")
        else:
            from app.mock_data import MOCK_RECIPES, MOCK_SIDES
            added = pantry_manager.seed_from_recipes(MOCK_RECIPES + MOCK_SIDES, mark_in_stock=True)

        return {
            "status": "success",
            "added_count": added,
            "stats": pantry_manager.get_stats(),
        }
    except Exception as e:
        logger.error(f"Error syncing pantry: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync pantry")


@app.post("/api/pantry/bulk-stock")
async def bulk_stock_pantry(in_stock: bool = True):
    """Set all pantry items to in-stock or out-of-stock."""
    try:
        items = pantry_manager.get_all_items()
        for it in items:
            pantry_manager.toggle_item(item_id=it["id"], in_stock=in_stock)
        return {
            "status": "success",
            "message": f"Updated {len(items)} items to {'in-stock' if in_stock else 'out-of-stock'}",
            "stats": pantry_manager.get_stats(),
        }
    except Exception as e:
        logger.error(f"Error bulk updating pantry: {e}")
        raise HTTPException(status_code=500, detail="Failed to bulk update pantry")


@app.post("/api/shopping-list/add")
async def add_missing_item_to_shopping_list(req: ShoppingListAddRequest):
    """Add a missing ingredient to Mealie's shopping list."""
    try:
        result = await mealie_client.add_to_shopping_list(
            item_name=req.item_name,
            note=req.note or (f"For recipe {req.recipe_id}" if req.recipe_id else "From Dinner Decider"),
        )
        return result
    except Exception as e:
        logger.error(f"Error adding to shopping list: {e}")
        raise HTTPException(status_code=500, detail="Failed to add to shopping list")


@app.get("/api/side-options")
async def get_side_options():
    """Fetch 3 curated side dish options from Mealie or smart fallbacks."""
    try:
        options = await mealie_client.get_side_options(count=3)
        return {
            "options": options,
            "count": len(options),
            "is_mock": mealie_client.mock_mode or any(o.get("is_mock") for o in options),
        }
    except Exception as e:
        logger.error(f"Error fetching side options: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch side options")


@app.get("/api/recipe-image/{recipe_id}")
async def get_recipe_image(recipe_id: str):
    """Proxy recipe image from Mealie, or return an elegant SVG fallback."""
    try:
        content, media_type = await mealie_client.get_recipe_image(recipe_id)
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving recipe image for {recipe_id}: {e}")
        raise HTTPException(status_code=404, detail="Image not found")


@app.get("/api/url-info")
async def get_url_info(url: str):
    """Inspect an external recipe URL and return its title and domain for instant UI preview."""
    try:
        title, domain = await fetch_recipe_url_info(url)
        return {
            "title": title,
            "domain": domain,
            "url": url,
        }
    except Exception as e:
        logger.warning(f"Error fetching URL info for {url}: {e}")
        return {
            "title": clean_domain(url),
            "domain": clean_domain(url),
            "url": url,
        }


@app.post("/api/choose")
async def choose_dinner(choice: DinnerChoice, background_tasks: BackgroundTasks):
    """Submit the chosen recipe or custom note, plus optional side dish to Mealie."""
    try:
        result = await mealie_client.submit_choice(
            recipe_id=choice.recipe_id.strip() if choice.recipe_id else None,
            custom_note=choice.custom_note.strip() if choice.custom_note else None,
            side_recipe_id=choice.side_recipe_id.strip() if choice.side_recipe_id else None,
            side_custom_note=choice.side_custom_note.strip() if choice.side_custom_note else None,
        )

        # Trigger push notification in background so UI confirmation never waits
        background_tasks.add_task(
            notifier.send_dinner_notification,
            dish_name=result.get("dish_name", "Dinner"),
            total_time=result.get("total_time"),
            recipe_slug=result.get("recipe_slug"),
            is_custom=result.get("is_custom", False),
            external_url=result.get("external_url"),
            side_name=result.get("side_name"),
            side_time=result.get("side_time"),
            side_slug=result.get("side_slug"),
            side_external_url=result.get("side_external_url"),
        )

        # Attach direct Mealie URLs if configured
        group = settings.mealie_group_slug or "home"
        if settings.mealie_base_url:
            recipe_slug = result.get("recipe_slug")
            result["mealie_url"] = (
                f"{settings.mealie_base_url}/g/{group}/r/{recipe_slug}"
                if recipe_slug
                else f"{settings.mealie_base_url}/g/{group}/planner"
            )
            side_slug = result.get("side_slug")
            if result.get("side_name"):
                result["side_mealie_url"] = (
                    f"{settings.mealie_base_url}/g/{group}/r/{side_slug}"
                    if side_slug
                    else f"{settings.mealie_base_url}/g/{group}/planner"
                )
            else:
                result["side_mealie_url"] = None
        else:
            result["mealie_url"] = None
            result["side_mealie_url"] = None

        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to submit dinner choice: {e}")
        # If Mealie is unreachable when submitting, still provide a clean error response
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update Mealie meal plan: {str(e)}",
        )


# Mount static files to serve index.html and assets
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
