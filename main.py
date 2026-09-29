import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator

from app.config import settings
from app.mealie_client import mealie_client

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
    }


@app.get("/api/options")
async def get_dinner_options():
    """Fetch 3 random dinner recipe options from Mealie (or mock recipes if unconfigured/offline)."""
    try:
        options = await mealie_client.get_dinner_options(count=3)
        return {
            "options": options,
            "count": len(options),
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


@app.post("/api/choose")
async def choose_dinner(choice: DinnerChoice):
    """Submit the chosen recipe or custom note to Mealie's Mealplanner API."""
    try:
        result = await mealie_client.submit_choice(
            recipe_id=choice.recipe_id.strip() if choice.recipe_id else None,
            custom_note=choice.custom_note.strip() if choice.custom_note else None,
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

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
