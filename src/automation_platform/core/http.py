from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Self

import httpx

from .logging import log_event


@dataclass(frozen=True, slots=True)
class HttpPolicy:
    timeout_seconds: float = 20.0
    retries: int = 3
    backoff_seconds: float = 1.0
    user_agent: str = "PersonalAutomationPlatform/0.1 (+respectful personal monitoring)"


class HttpClient:
    def __init__(self, policy: HttpPolicy | None = None, transport: httpx.BaseTransport | None = None):
        self.policy = policy or HttpPolicy()
        self.requests_count = 0
        self._logger = logging.getLogger(__name__)
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=self.policy.timeout_seconds,
            headers={"User-Agent": self.policy.user_agent, "Accept": "text/html,application/json"},
            transport=transport,
        )

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.policy.retries):
            try:
                self.requests_count += 1
                response = self._client.get(url)
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                log_event(self._logger, logging.WARNING, "http_retry", url=url, attempt=attempt + 1)
                if attempt + 1 < self.policy.retries:
                    delay = self.policy.backoff_seconds * (2**attempt) + random.uniform(0, 0.25)
                    time.sleep(delay)
        assert last_error is not None
        raise last_error

    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        self.requests_count += 1
        response = self._client.post(url, json=payload)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise TypeError("Expected JSON object")
        return value

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
