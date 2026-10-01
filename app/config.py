import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    mealie_base_url: str = os.getenv("MEALIE_BASE_URL", "").rstrip("/")
    mealie_api_token: str = os.getenv("MEALIE_API_TOKEN", "").strip()
    mealie_group_slug: str = os.getenv("MEALIE_GROUP_SLUG", "home").strip() or "home"
    port: int = int(os.getenv("PORT", "8000"))
    mock_mode: bool = os.getenv("MOCK_MODE", "").lower() in ("true", "1", "yes")

    # Notification Settings (ntfy.sh or self-hosted ntfy)
    ntfy_topic: str = os.getenv("NTFY_TOPIC", "").strip()
    ntfy_base_url: str = os.getenv("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    ntfy_token: str = os.getenv("NTFY_TOKEN", "").strip()

    # Pantry Inventory Database Path
    pantry_db_path: str = os.getenv("PANTRY_DB_PATH", "data/pantry.db")

    @property
    def is_configured(self) -> bool:
        return bool(self.mealie_base_url and self.mealie_api_token)

    @property
    def is_ntfy_configured(self) -> bool:
        return bool(self.ntfy_topic)


settings = Settings()
