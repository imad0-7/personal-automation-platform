from __future__ import annotations

from dotenv import load_dotenv

from automation_platform.core.config import PlatformSettings
from automation_platform.core.http import HttpClient, HttpPolicy
from automation_platform.core.models import Notification, Priority
from automation_platform.integrations.telegram import TelegramNotifier


def main() -> int:
    load_dotenv()
    settings = PlatformSettings.from_env()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    with HttpClient(HttpPolicy(timeout_seconds=15, retries=1)) as http:
        notifier = TelegramNotifier(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            http,
        )
        notifier.notify(
            Notification(
                title="TEST — Personal Automation Platform",
                message=(
                    "La connexion Telegram fonctionne.\n\n"
                    "Le moniteur Cash Converters est actif et son état initial est enregistré."
                ),
                priority=Priority.NORMAL,
                url="https://github.com/imad0-7/personal-automation-platform/actions",
            )
        )

    print("Telegram test notification sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
