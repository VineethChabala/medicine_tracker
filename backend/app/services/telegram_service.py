"""
Telegram notification service — wraps the Bot API sendMessage endpoint.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_telegram_message(chat_id: int, text: str) -> bool:
    """
    Sends a Markdown-formatted message to a Telegram chat.
    Returns True on success, False on failure.
    """
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram send failed to chat_id={chat_id}: {e}")
    return False


async def set_webhook(webhook_url: str) -> bool:
    """Registers the FastAPI webhook URL with Telegram."""
    if not settings.telegram_bot_token:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"url": webhook_url})
            result = resp.json()
            logger.info(f"Telegram setWebhook result: {result}")
            return result.get("ok", False)
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
    return False


_bot_username = None

async def get_bot_username() -> str:
    """Fetches the bot username from Telegram getMe API and caches it."""
    global _bot_username
    if _bot_username:
        return _bot_username
    if not settings.telegram_bot_token:
        return "medicine_refill_tracker_bot"
    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                _bot_username = resp.json().get("result", {}).get("username")
                return _bot_username
    except Exception as e:
        logger.error(f"Failed to fetch bot username: {e}")
    return "medicine_refill_tracker_bot"
