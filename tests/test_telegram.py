import json

import httpx

from automation_platform.core.http import HttpClient
from automation_platform.core.models import Notification, Priority
from automation_platform.integrations.telegram import TelegramNotifier


def test_telegram_adapter_sends_structured_message():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier("fake-token", "42", client)
        notifier.notify(Notification(
            title="Nouvelle annonce", message="RTX 4070 à 699 €",
            priority=Priority.URGENT, url="https://example.test/item",
        ))

    assert captured["chat_id"] == "42"
    assert "RTX 4070" in captured["text"]
    assert "Voir l’annonce" in captured["text"]
