from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from automation_platform.core.config import PlatformSettings
from automation_platform.core.database import repository_from_url
from automation_platform.core.http import HttpClient, HttpPolicy
from automation_platform.core.logging import configure_logging
from automation_platform.core.models import RunStatus
from automation_platform.core.notifications import ConsoleNotifier
from automation_platform.integrations.telegram import TelegramNotifier

from .config import CashConvertersConfig
from .scraper import CashConvertersScraper
from .service import CashConvertersAutomation


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Cash Converters Belgium")
    parser.add_argument("--config", type=Path, help="Alternative YAML configuration")
    args = parser.parse_args()
    load_dotenv()
    settings = PlatformSettings.from_env()
    configure_logging(settings.log_level)
    config = CashConvertersConfig.load(args.config)
    repository = repository_from_url(settings.database_url)
    repository.migrate()
    with HttpClient(HttpPolicy()) as http:
        if settings.notification_backend == "telegram":
            notifier = TelegramNotifier(
                settings.telegram_bot_token or "", settings.telegram_chat_id or "", http
            )
        elif settings.notification_backend == "console":
            notifier = ConsoleNotifier()
        else:
            raise ValueError(f"Unknown NOTIFICATION_BACKEND: {settings.notification_backend}")
        summary = CashConvertersAutomation(
            repository, CashConvertersScraper(http, config), notifier, config
        ).run()
    repository.close()
    print(json.dumps({
        "automation": summary.automation,
        "status": summary.status.value,
        "observed": summary.observed,
        "discovered": summary.discovered,
        "requests": summary.requests_count,
        "notifications": summary.notifications_sent,
        "errors": summary.errors,
    }, ensure_ascii=False))
    return 0 if summary.status == RunStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
