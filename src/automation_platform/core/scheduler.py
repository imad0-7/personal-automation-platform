from __future__ import annotations

import logging
import time
from collections.abc import Callable


def run_every(interval_seconds: int, job: Callable[[], object]) -> None:
    """Small portable loop for Docker/homelab use; cloud schedulers call the CLI directly."""
    logger = logging.getLogger(__name__)
    while True:
        started = time.monotonic()
        try:
            job()
        except Exception:
            logger.exception("scheduled_job_failed")
        elapsed = time.monotonic() - started
        time.sleep(max(0, interval_seconds - elapsed))
