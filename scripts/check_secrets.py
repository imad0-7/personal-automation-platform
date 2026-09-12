from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATTERNS = {
    "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "Telegram bot token": re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files"], check=True, text=True, capture_output=True)
    return [Path(line) for line in result.stdout.splitlines() if line]


def main() -> int:
    findings = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path}: possible {name}")
    if findings:
        print("\n".join(findings))
        return 1
    print("No obvious secrets found in tracked text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
