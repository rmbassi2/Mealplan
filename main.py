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
from app.url_helper import fetch_recipe_url_info, clean_domain

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dinner_decider")

app = FastAPI(
    title="Dinner Decider",
    description="A lightweight, mobile-first dinner voting web app integrated with Mealie.",
    version="1.0.0",
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

    @model_validator(mode="after")
    def validate_choice(self):
        has_recipe = bool(self.recipe_id and self.recipe_id.strip())
        has_custom = bool(self.custom_note and self.custom_note.strip())
        if not has_recipe and not has_custom:
            raise ValueError("Either recipe_id or custom_note must be provided.")
        return self


@app.get("/health")
async def health_check():
    """Healthcheck endpoint for container and deployment monitors."""
    return {
        "status": "healthy",
        "mock_mode": mealie_client.mock_mode,
        "mealie_configured": settings.is_configured,
        "base_url": settings.mealie_base_url or "(none)",
        "ntfy_configured": settings.is_ntfy_configured,
        "ntfy_topic": settings.ntfy_topic or "(none)",
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
            return {
                "has_plan": True,
                "plan": {
                    **plan,
                    "mealie_url": link,
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
            {"id": "quick", "label": "Quick (<30m)", "icon": "⚡"},
            {"id": "comfort", "label": "Comfort Food", "icon": "🍲"},
            {"id": "fresh", "label": "Light & Fresh", "icon": "🥗"},
            {"id": "chicken", "label": "Chicken", "icon": "🍗"},
            {"id": "beef", "label": "Beef", "icon": "🥩"},
            {"id": "seafood", "label": "Seafood", "icon": "🐟"},
            {"id": "vegetarian", "label": "Vegetarian", "icon": "🥑"},
            {"id": "sheet-pan", "label": "Sheet Pan", "icon": "🥘"},
            {"id": "air-fryer", "label": "Air Fryer", "icon": "💨"},
            {"id": "slow-cooker", "label": "Slow Cooker", "icon": "⏳"},
        ],
    }


@app.get("/api/options")
async def get_dinner_options(
    mood: Optional[str] = None,
    protein: Optional[str] = None,
    tool: Optional[str] = None,
    cuisine: Optional[str] = None,
):
    """Fetch 3 balanced dinner recipe options from Mealie, with optional mood, protein, tool, or cuisine filtering."""
    try:
        options = await mealie_client.get_dinner_options(
            count=3,
            mood=mood,
            protein=protein,
            tool=tool,
            cuisine=cuisine,
        )
        return {
            "options": options,
            "count": len(options),
            "active_filters": {
                "mood": mood,
                "protein": protein,
                "tool": tool,
                "cuisine": cuisine,
            },
            "is_mock": mealie_client.mock_mode or any(o.get("is_mock") for o in options),
        }
    except Exception as e:
        logger.error(f"Error fetching dinner options: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dinner options")


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
    """Submit the chosen recipe or custom note to Mealie's Mealplanner API and notify the chef."""
    try:
        result = await mealie_client.submit_choice(
            recipe_id=choice.recipe_id.strip() if choice.recipe_id else None,
            custom_note=choice.custom_note.strip() if choice.custom_note else None,
        )

        # Trigger push notification in background so UI confirmation never waits
        background_tasks.add_task(
            notifier.send_dinner_notification,
            dish_name=result.get("dish_name", "Dinner"),
            total_time=result.get("total_time"),
            recipe_slug=result.get("recipe_slug"),
            is_custom=result.get("is_custom", False),
            external_url=result.get("external_url"),
        )

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
