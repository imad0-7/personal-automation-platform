import json

from ..models import Notification


class ConsoleNotifier:
    backend_name = "console"

    def notify(self, notification: Notification) -> None:
        print(json.dumps({
            "notification": notification.title,
            "message": notification.message,
            "priority": notification.priority.value,
            "url": notification.url,
        }, ensure_ascii=False))
