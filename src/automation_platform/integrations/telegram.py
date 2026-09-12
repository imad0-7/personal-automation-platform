from __future__ import annotations

from automation_platform.core.http import HttpClient
from automation_platform.core.models import Notification


class TelegramNotifier:
    backend_name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, http: HttpClient):
        if not bot_token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
        self._endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._http = http

    def notify(self, notification: Notification) -> None:
        icon = "🔥" if notification.priority.value == "urgent" else "🆕"
        text = f"{icon} <b>{notification.title}</b>\n\n{notification.message}"
        if notification.url:
            text += f'\n\n<a href="{notification.url}">Voir l’annonce</a>'
        result = self._http.post_json(self._endpoint, {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        })
        if result.get("ok") is not True:
            raise RuntimeError("Telegram rejected the notification")
