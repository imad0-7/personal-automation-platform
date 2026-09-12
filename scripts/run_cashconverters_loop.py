from __future__ import annotations

import os
import subprocess
import sys

from automation_platform.core.scheduler import run_every


def run_once() -> None:
    subprocess.run(
        [sys.executable, "-m", "automations.cashconverters.run"],
        check=False,
    )


if __name__ == "__main__":
    minutes = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    run_every(minutes * 60, run_once)
