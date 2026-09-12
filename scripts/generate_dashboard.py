from __future__ import annotations

import html
import json
from pathlib import Path

from dotenv import load_dotenv

from automation_platform.core.config import PlatformSettings
from automation_platform.core.database import repository_from_url


def build_html(repo) -> str:
    state = repo.state('cashconverters-v2', 'last_status', {})
    cards = []
    for listing in repo.recent_listings('cashconverters', 100):
        attrs = listing.attributes
        fields = attrs.get('hardware', {}).get('fields', {})
        specs = ' · '.join(html.escape(str(v.get('value'))) for v in fields.values()
                         if v.get('value') is not None and not isinstance(v.get('value'), list))
        reasons = attrs.get('offer_reasons', [])
        kind = 'offer' if reasons else 'listing'
        price = f'{listing.price_cents / 100:.2f} €' if listing.price_cents is not None else '? €'
        reservable = attrs.get('reservable')
        availability = 'Réservable' if reservable is True else 'Indisponible' if reservable is False else 'Non vérifié'
        cards.append(f'''<article class="card {kind}">
          <div class="badges"><span>{'🔥 Offre' if reasons else 'PC'}</span><span>{availability}</span></div>
          <h2>{html.escape(listing.title)}</h2><p class="price">{price}</p>
          <p>{specs or 'Caractéristiques à analyser'}</p>
          <p>{html.escape(' · '.join(reasons))}</p>
          <a href="{html.escape(listing.url, quote=True)}" rel="noopener">Voir l’annonce</a>
        </article>''')
    status = html.escape(json.dumps(state, ensure_ascii=False))
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Automation Platform</title>
<style>
:root{{--bg:#0b1020;--panel:#151c30;--text:#edf2ff;--muted:#9da9c7;--accent:#7c9cff;--hot:#ff725e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:end}}
.status{{color:var(--muted);font-size:12px;word-break:break-word}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px;margin-top:24px}}
.card{{background:var(--panel);padding:18px;border-radius:14px;border:1px solid #26304b}}.offer{{border-color:var(--hot)}}
h1{{margin:0}}h2{{font-size:16px;min-height:42px}}.price{{font-size:24px;font-weight:700}}p{{color:var(--muted)}}
.badges{{display:flex;justify-content:space-between;color:var(--accent);font-size:12px}}a{{color:#a9bcff}}
</style></head><body><main><header><div><h1>Personal Automation Platform</h1>
<p>Cash Converters · 100 ordinateurs récents</p></div><div class="status">{status}</div></header>
<section class="grid">{''.join(cards) or '<p>Aucune donnée disponible.</p>'}</section></main></body></html>'''


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
