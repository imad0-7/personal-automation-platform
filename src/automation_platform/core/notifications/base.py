from typing import Protocol

from ..models import Notification


class Notifier(Protocol):
    backend_name: str

    def notify(self, notification: Notification) -> None: ...
