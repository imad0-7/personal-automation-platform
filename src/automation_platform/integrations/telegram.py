from __future__ import annotations

import html

import httpx

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
        text = f"{icon} <b>{html.escape(notification.title)}</b>\n\n{notification.message}"
        if notification.url:
            text += f'\n\n<a href="{html.escape(notification.url, quote=True)}">Voir l’annonce</a>'
        try:
            result = self._http.post_json(self._endpoint, {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            })
        except httpx.HTTPError as exc:
            # Telegram puts credentials in its URL; never let an HTTP traceback leak it.
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 'network'
            raise RuntimeError(f'Telegram delivery failed ({code})') from None
        if result.get("ok") is not True:
            raise RuntimeError("Telegram rejected the notification")

    def get_updates(self, offset: int) -> list[dict]:
        try:
            result = self._http.post_json(self._endpoint.replace('/sendMessage', '/getUpdates'), {
                'offset': offset, 'timeout': 0, 'allowed_updates': ['message'],
            })
        except httpx.HTTPError:
            raise RuntimeError('Telegram command polling failed') from None
        if result.get('ok') is not True:
            raise RuntimeError('Telegram command polling rejected')
        return result.get('result', [])

    @property
    def chat_id(self) -> str:
        return self._chat_id
