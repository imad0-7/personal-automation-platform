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
        prefix = notification.metadata.get("telegram_prefix")
        if prefix:
            text = html.escape(str(prefix)) + "\n\n" + text
        if notification.url:
            text += f'\n\n<a href="{html.escape(notification.url, quote=True)}">Voir l’annonce</a>'
        payload = {
            "chat_id": self._chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        if notification.metadata.get('reply_markup'):
            payload['reply_markup'] = notification.metadata['reply_markup']
        try:
            result = self._http.post_json(self._endpoint, payload)
        except httpx.HTTPError as exc:
            # Telegram puts credentials in its URL; never let an HTTP traceback leak it.
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 'network'
            raise RuntimeError(f'Telegram delivery failed ({code})') from None
        if result.get("ok") is not True:
            raise RuntimeError("Telegram rejected the notification")

    def get_updates(self, offset: int) -> list[dict]:
        try:
            result = self._http.post_json(self._endpoint.replace('/sendMessage', '/getUpdates'), {
                'offset': offset, 'timeout': 0, 'allowed_updates': ['message', 'callback_query'],
            })
        except httpx.HTTPError:
            raise RuntimeError('Telegram command polling failed') from None
        if result.get('ok') is not True:
            raise RuntimeError('Telegram command polling rejected')
        return result.get('result', [])

    def answer_callback(self, query_id: str) -> None:
        try:
            result = self._http.post_json(self._endpoint.replace('/sendMessage', '/answerCallbackQuery'), {
                'callback_query_id': query_id, 'text': 'Action reçue. Réponse dans la conversation.',
            })
        except httpx.HTTPError:
            # With scheduled polling Telegram may already have expired the popup;
            # the requested action and its durable reply still need to be processed.
            return
        if result.get('ok') is not True:
            return

    @property
    def chat_id(self) -> str:
        return self._chat_id
