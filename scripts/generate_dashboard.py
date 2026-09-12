from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from automation_platform.core.config import PlatformSettings
from automation_platform.core.database import repository_from_url
from automations.cashconverters.dashboard import build_html


def main() -> int:
    load_dotenv()
    repo = repository_from_url(PlatformSettings.from_env().database_url)
    repo.migrate()
    output = Path('public/index.html')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(repo), encoding='utf-8')
    repo.close()
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
