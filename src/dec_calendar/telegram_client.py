from __future__ import annotations

import logging

import requests

from dec_calendar.config import Settings

logger = logging.getLogger(__name__)


class TelegramSendError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_telegram()
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.verify_ssl = not settings.telegram_disable_ssl_verify

    def send_message(self, text: str, *, timeout_s: int = 20) -> None:
        if not text.strip():
            raise TelegramSendError("Telegram message text is empty")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=timeout_s,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise TelegramSendError(f"Telegram request failed: {exc}") from exc

        if response.status_code != 200:
            raise TelegramSendError(
                f"Telegram API error HTTP {response.status_code}: {response.text[:500]}"
            )
        logger.info("Telegram message sent to chat_id=%s", self.chat_id)
