import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from main import app
from app.notifier import NtfyNotifier


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_notifier_not_configured():
    notifier = NtfyNotifier()
    notifier.topic = ""  # Force unconfigured
    result = await notifier.send_dinner_notification("Pizza", is_custom=False)
    assert result is False


@pytest.mark.anyio
async def test_notifier_send_recipe_success():
    notifier = NtfyNotifier()
    notifier.topic = "test-dinner-topic"
    notifier.base_url = "https://ntfy.sh"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        success = await notifier.send_dinner_notification(
            dish_name="Crispy Honey Garlic Salmon",
            total_time="25 mins",
            recipe_slug="crispy-honey-garlic-salmon",
            is_custom=False,
        )

        assert success is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["topic"] == "test-dinner-topic"
        assert "Crispy Honey Garlic Salmon" in payload["title"]
        assert payload["priority"] == 4
        assert "pot_of_food" in payload["tags"]


@pytest.mark.anyio
async def test_notifier_send_custom_craving():
    notifier = NtfyNotifier()
    notifier.topic = "test-dinner-topic"
    notifier.base_url = "https://ntfy.sh"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        success = await notifier.send_dinner_notification(
            dish_name="Spicy Thai Green Curry Takeout",
            is_custom=True,
        )

        assert success is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "Custom Craving" in payload["title"]
        assert "Spicy Thai Green Curry Takeout" in payload["message"]
