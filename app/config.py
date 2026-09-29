import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    mealie_base_url: str = os.getenv("MEALIE_BASE_URL", "").rstrip("/")
    mealie_api_token: str = os.getenv("MEALIE_API_TOKEN", "").strip()
    port: int = int(os.getenv("PORT", "8000"))
    mock_mode: bool = os.getenv("MOCK_MODE", "").lower() in ("true", "1", "yes")

    @property
    def is_configured(self) -> bool:
        return bool(self.mealie_base_url and self.mealie_api_token)


settings = Settings()
