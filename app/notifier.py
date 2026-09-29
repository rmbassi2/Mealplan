import logging
from typing import Any, Dict, Optional
import httpx

from app.config import settings

logger = logging.getLogger("dinner_notifier")


class NtfyNotifier:
    """Sends rich push notifications to mobile devices via ntfy.sh or a self-hosted ntfy server."""

    def __init__(self):
        self.base_url = settings.ntfy_base_url.rstrip("/")
        self.topic = settings.ntfy_topic.strip()
        self.token = settings.ntfy_token.strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.topic)

    async def send_dinner_notification(
        self,
        dish_name: str,
        total_time: Optional[str] = None,
        recipe_slug: Optional[str] = None,
        is_custom: bool = False,
    ) -> bool:
        """Send a rich push notification to the configured ntfy topic.

        Non-blocking, catches all errors so notification failures never disrupt the user UI.
        """
        if not self.is_configured:
            logger.info("Ntfy notification skipped (NTFY_TOPIC is not set in .env).")
            return False

        topic_url = f"{self.base_url}/{self.topic}"

        # Determine click destination
        click_url = None
        if settings.mealie_base_url:
            if recipe_slug:
                click_url = f"{settings.mealie_base_url}/recipe/{recipe_slug}"
            else:
                click_url = f"{settings.mealie_base_url}/household/mealplan/planner/view"

        # Build notification content
        if is_custom:
            title = "🍲 Tonight's Dinner: Custom Craving!"
            message = (
                f"Special dinner request locked in:\n\n"
                f"👉 {dish_name}\n\n"
                f"Scheduled for tonight in your Mealie meal plan."
            )
            tags = ["fork_and_knife", "bell"]
        else:
            time_str = f" (⏱️ {total_time})" if total_time else ""
            title = f"🍲 Tonight's Dinner: {dish_name}"
            message = (
                f"Tonight's menu selection is locked in:\n\n"
                f"👉 {dish_name}{time_str}\n\n"
                f"Scheduled for tonight in your Mealie meal plan. Time to get cooking! 👩‍🍳"
            )
            tags = ["pot_of_food", "tada"]

        payload: Dict[str, Any] = {
            "topic": self.topic,
            "title": title,
            "message": message,
            "priority": 4,  # High priority (ring & vibrate)
            "tags": tags,
        }

        if click_url:
            payload["click"] = click_url
            payload["actions"] = [
                {
                    "action": "view",
                    "label": "Open in Mealie",
                    "url": click_url,
                    "clear": False,
                }
            ]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            logger.info(f"Sending ntfy push notification to {topic_url}...")
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(topic_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"Successfully delivered ntfy notification to topic '{self.topic}'.")
                    return True
                else:
                    logger.warning(
                        f"ntfy.sh returned HTTP {resp.status_code}: {resp.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to deliver ntfy notification ({e}).")
            return False


notifier = NtfyNotifier()
