from datetime import date
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
        external_url: Optional[str] = None,
        side_name: Optional[str] = None,
        side_time: Optional[str] = None,
        side_slug: Optional[str] = None,
        side_external_url: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> bool:
        """Send a rich push notification to the configured ntfy topic.

        Non-blocking, catches all errors so notification failures never disrupt the user UI.
        """
        if not self.is_configured:
            logger.info("Ntfy notification skipped (NTFY_TOPIC is not set in .env).")
            return False

        today_iso = date.today().isoformat()
        is_today = not target_date or target_date == today_iso

        day_heading = "Tonight"
        day_sched_text = "tonight's meal plan"
        if not is_today:
            try:
                dt = date.fromisoformat(target_date)
                day_heading = f"{dt.strftime('%A')}"
                day_sched_text = f"{dt.strftime('%A, %b %d')} on Mealie"
            except Exception:
                day_heading = target_date or "Planned"
                day_sched_text = f"{target_date} on Mealie"

        # In ntfy, JSON payloads must be POSTed to the root server URL (e.g. https://ntfy.sh/)
        # with the 'topic' field inside the JSON body.
        publish_url = f"{self.base_url}/"

        actions = []
        side_snippet = f"\n🥗 Side: {side_name}" + (f" (⏱️ {side_time})" if side_time else "") if side_name else ""

        # Determine click destination and content
        if external_url:
            from urllib.parse import urlparse
            domain = urlparse(external_url).netloc.replace("www.", "")
            title = f"{day_heading}'s Dinner: Web Recipe Request!" + (f" ({dish_name} + {side_name})" if side_name else "")
            message = (
                f"Special web recipe request locked in:\n\n"
                f"🌐 {dish_name}\n"
                f"Source: {domain}"
                f"{side_snippet}\n\n"
                f"Scheduled on {day_sched_text} (cookbook untouched)."
            )
            tags = ["globe_with_meridians", "bell"]
            click_url = external_url
            actions.append(
                {
                    "action": "view",
                    "label": f"Open on {domain}",
                    "url": external_url,
                    "clear": False,
                }
            )
            if settings.mealie_base_url:
                group = settings.mealie_group_slug or "home"
                actions.append(
                    {
                        "action": "view",
                        "label": "Open Meal Plan",
                        "url": f"{settings.mealie_base_url}/g/{group}/planner",
                        "clear": False,
                    }
                )
        elif is_custom:
            click_url = None
            if settings.mealie_base_url:
                group = settings.mealie_group_slug or "home"
                click_url = f"{settings.mealie_base_url}/g/{group}/planner"
            title = f"{day_heading}'s Dinner: Custom Craving!" + (f" ({dish_name} + {side_name})" if side_name else "")
            message = (
                f"Special dinner request locked in:\n"
                f"🍜 {dish_name}"
                f"{side_snippet}\n\n"
                f"Scheduled on {day_sched_text}."
            )
            tags = ["fork_and_knife", "bell"]
            if click_url:
                actions.append(
                    {
                        "action": "view",
                        "label": "Open Meal Plan",
                        "url": click_url,
                        "clear": False,
                    }
                )
        else:
            click_url = None
            if settings.mealie_base_url and recipe_slug:
                group = settings.mealie_group_slug or "home"
                click_url = f"{settings.mealie_base_url}/g/{group}/r/{recipe_slug}"
            time_str = f" • ⏱️ {total_time}" if total_time else ""
            title = f"{day_heading}'s Dinner: {dish_name}" + (f" + {side_name}" if side_name else "")
            message = (
                f"{day_heading}'s menu is locked in!\n\n"
                f"🍽️ {dish_name}{time_str}"
                f"{side_snippet}\n\n"
                f"Scheduled on {day_sched_text}. Time to get cooking! 👩‍🍳"
            )
            tags = ["pot_of_food", "tada"]
            if click_url:
                actions.append(
                    {
                        "action": "view",
                        "label": "Open Recipe",
                        "url": click_url,
                        "clear": False,
                    }
                )

        # Add side recipe action button if available
        if side_external_url:
            from urllib.parse import urlparse
            s_domain = urlparse(side_external_url).netloc.replace("www.", "")
            actions.append(
                {
                    "action": "view",
                    "label": f"Open Side ({s_domain})",
                    "url": side_external_url,
                    "clear": False,
                }
            )
        elif side_slug and settings.mealie_base_url:
            group = settings.mealie_group_slug or "home"
            actions.append(
                {
                    "action": "view",
                    "label": f"Open Side ({side_name})",
                    "url": f"{settings.mealie_base_url}/g/{group}/r/{side_slug}",
                    "clear": False,
                }
            )

        payload: Dict[str, Any] = {
            "topic": self.topic,
            "title": title,
            "message": message,
            "priority": 4,  # High priority (ring & vibrate)
            "tags": tags,
            "markdown": True,
        }

        if click_url:
            payload["click"] = click_url
        if actions:
            payload["actions"] = actions

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            logger.info(f"Sending ntfy push notification for topic '{self.topic}' to {publish_url}...")
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(publish_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"Successfully delivered ntfy notification to topic '{self.topic}'.")
                    return True
                else:
                    logger.warning(
                        f"ntfy server returned HTTP {resp.status_code}: {resp.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to deliver ntfy notification: {e}")
            return False


notifier = NtfyNotifier()
