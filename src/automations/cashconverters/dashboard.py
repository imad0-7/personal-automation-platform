from __future__ import annotations

import html
from collections import Counter
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BRUSSELS = ZoneInfo('Europe/Brussels')


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _field(listing, name: str, default: str = 'Inconnu') -> str:
    value = listing.attributes.get('hardware', {}).get('fields', {}).get(name, {}).get('value')
    return str(value) if value not in (None, '') else default


def _availability(listing) -> tuple[str, str]:
    value = listing.attributes.get('reservable')
    if value is True:
        return 'Réservable', 'available'
    if value is False:
        return 'Non réservable', 'unavailable'
    return 'À vérifier', 'unknown'


def _card(listing, detected_at: datetime | None = None) -> str:
    reasons = listing.attributes.get('offer_reasons', [])
    availability, availability_key = _availability(listing)
    price = f'{listing.price_cents / 100:,.2f} €'.replace(',', ' ') if listing.price_cents is not None else '? €'
    rank = listing.attributes.get('catalog_rank', '?')
    platform = _field(listing, 'platform')
    cpu, gpu = _field(listing, 'cpu'), _field(listing, 'gpu')
    ram = _field(listing, 'ram_gb', 'RAM inconnue')
    ram = f'{ram} Go' if ram != 'RAM inconnue' else ram
    image = (f'<img loading="lazy" src="{_e(listing.image_url)}" alt="">'
             if listing.image_url else '<div class="no-image">PC</div>')
    search = ' '.join([listing.title, platform, cpu, gpu, listing.store or '']).casefold()
    reason = f'<p class="reason">{_e(" · ".join(reasons))}</p>' if reasons else ''
    detected = ''
    if detected_at is not None:
        local = detected_at.astimezone(BRUSSELS)
        detected = f'<p class="detected">Détecté à {local:%H:%M} le {local:%d/%m/%Y}</p>'
    return f'''<article class="product {'offer' if reasons else ''}" data-search="{_e(search)}"
      data-availability="{availability_key}" data-platform="{_e(platform)}">
      <div class="visual">{image}<span class="rank">#{_e(rank)}</span></div>
      <div class="product-body"><div class="badges">
        <span class="badge {'hot' if reasons else ''}">{'🔥 Offre' if reasons else 'Nouveau catalogue'}</span>
        <span class="badge {availability_key}">{_e(availability)}</span>
      </div><h3>{_e(listing.title)}</h3><div class="price">{price}</div>
      <p class="specs">{_e(platform)} · {_e(cpu)} · {_e(gpu)} · {_e(ram)}</p>
      <p class="store">{_e(listing.store or 'Magasin inconnu')}</p>{detected}{reason}
      <a class="action" href="{_e(listing.url)}" target="_blank" rel="noopener">Voir l’annonce ↗</a>
      </div></article>'''


def _bars(values: Counter, total: int) -> str:
    if not values:
        return '<p class="empty">Pas encore de données analysées.</p>'
    rows = []
    for name, count in values.most_common(6):
        width = max(4, round(count / max(total, 1) * 100))
        rows.append(f'''<div class="bar-row"><div><span>{_e(name)}</span><strong>{count}</strong></div>
        <div class="track"><i style="width:{width}%"></i></div></div>''')
    return ''.join(rows)


def _hour_chart(discoveries: list[tuple[object, datetime]]) -> str:
    counts = Counter(seen.astimezone(BRUSSELS).hour for _, seen in discoveries)
    peak = max(counts.values(), default=0)
    if not peak:
        return '<p class="empty">Pas encore assez de nouveautés après l’état initial.</p>'
    columns = []
    for hour in range(24):
        count = counts[hour]
        height = round(count / peak * 100) if count else 0
        columns.append(f'''<div class="hour" title="{hour:02d}h–{hour + 1:02d}h : {count} ajout(s)">
          <strong>{count or ''}</strong><i style="height:{height}%"></i><span>{hour:02d}h</span></div>''')
    return '<div class="chart-scroll"><div class="hour-chart">' + ''.join(columns) + '</div></div>'


def build_html(repo) -> str:
    listings = repo.recent_listings('cashconverters', 100)
    discoveries = repo.listing_discoveries('cashconverters', 'cashconverters')
    state = repo.state('cashconverters-v2', 'last_status', {})
    changes = repo.recent_price_changes('cashconverters', 30)
    offers = [x for x in listings if x.attributes.get('offer_reasons')]
    clarifications = [x for x in listings if x.attributes.get('detail_checked')
                      and x.attributes.get('hardware', {}).get('questions')]
    available = [x for x in listings if x.attributes.get('reservable') is True]
    unavailable = [x for x in listings if x.attributes.get('reservable') is False]
    analyzed = [x for x in listings if x.attributes.get('hardware', {}).get('fields')]
    total = max([int(x.attributes.get('catalog_total') or 0) for x in listings] or [0])
    platforms = Counter(_field(x, 'platform') for x in listings)
    stores = Counter(x.store or 'Inconnu' for x in listings)
    cards = {x.external_id: _card(x) for x in listings}
    status = state.get('status', 'INCONNU')
    status_class = 'ok' if status == 'SUCCESS' else 'bad'
    last_scan = state.get('finished_at', 'Pas encore de scan')
    errors = len(state.get('errors', []))
    now_local = datetime.now(UTC).astimezone(BRUSSELS)
    today = [(item, seen) for item, seen in discoveries
             if seen.astimezone(BRUSSELS).date() == now_local.date()]
    last_discovery = discoveries[0][1].astimezone(BRUSSELS) if discoveries else None
    last_discovery_time = f'{last_discovery:%H:%M}' if last_discovery else 'Aucune'
    last_discovery_date = f'{last_discovery:%d/%m/%Y}' if last_discovery else 'depuis l’activation'
    discovery_cards = ''.join(_card(item, seen) for item, seen in today)

    change_rows = []
    for item in changes:
        delta = item['price_cents'] - item['old_price']
        change_rows.append(f'''<tr><td><a href="{_e(item['url'])}" target="_blank">{_e(item['title'])}</a></td>
          <td>{item['old_price'] / 100:.2f} €</td><td>{item['price_cents'] / 100:.2f} €</td>
          <td class="{'down' if delta < 0 else 'up'}">{delta / 100:+.2f} €</td>
          <td>{_e(item['observed_at'][:16].replace('T', ' '))}</td></tr>''')
    changed = ''.join(change_rows) or '<tr><td colspan="5" class="empty">Aucun changement de prix enregistré.</td></tr>'
    generated = datetime.now(UTC).isoformat(timespec='minutes')

    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Automation Platform</title>
<style>
:root{{--bg:#08101f;--panel:#111b2e;--panel2:#17243b;--line:#263856;--text:#f4f7ff;--muted:#91a1bd;--blue:#7295ff;--cyan:#54d5d0;--hot:#ff735c;--green:#61d69b;--yellow:#ffca6b}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 10% 0,#142547 0,transparent 34%),var(--bg);color:var(--text);font:15px Inter,system-ui,sans-serif}}
button,input,select{{font:inherit}}a{{color:inherit}}main{{max-width:1280px;margin:auto;padding:30px 22px 60px}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:24px}}h1{{font-size:clamp(25px,4vw,42px);margin:3px 0}}.eyebrow{{color:var(--cyan);text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:800}}
.sub,.muted,.store,.specs,.detected{{color:var(--muted)}}.health{{text-align:right}}.health strong{{display:inline-block;padding:7px 10px;border-radius:99px;background:#1b2a43}}.health .ok{{color:var(--green)}}.health .bad{{color:var(--hot)}}
.tabs{{display:flex;gap:8px;overflow:auto;padding-bottom:4px;position:sticky;top:0;z-index:5;background:rgba(8,16,31,.92);backdrop-filter:blur(12px)}}.tab{{border:1px solid var(--line);background:var(--panel);color:var(--muted);padding:10px 14px;border-radius:10px;white-space:nowrap;cursor:pointer}}.tab.active{{color:white;background:#253b67;border-color:#4162a4}}
.view{{display:none;padding-top:22px}}.view.active{{display:block}}.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}}.kpi{{background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);padding:16px;border-radius:15px}}.kpi span{{color:var(--muted);font-size:12px}}.kpi strong{{display:block;font-size:28px;margin-top:5px}}.kpi.hot strong{{color:var(--hot)}}.kpi small{{display:block;color:var(--muted);margin-top:3px}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}}.panel{{background:rgba(17,27,46,.88);border:1px solid var(--line);border-radius:16px;padding:18px}}.panel h2,.section-head h2{{margin:0 0 15px;font-size:18px}}
.bar-row{{margin:12px 0}}.bar-row>div:first-child{{display:flex;justify-content:space-between;margin-bottom:6px}}.track{{height:7px;background:#22304a;border-radius:9px;overflow:hidden}}.track i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--cyan));border-radius:9px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}.product{{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden;display:flex;flex-direction:column}}.product.offer{{border-color:#a5534b;box-shadow:0 0 0 1px #6e3732}}
.visual{{height:150px;background:#0c1527;position:relative;display:grid;place-items:center;overflow:hidden}}.visual img{{width:100%;height:100%;object-fit:contain}}.no-image{{font-size:32px;color:#344762}}.rank{{position:absolute;top:10px;right:10px;background:#07101dcc;padding:5px 8px;border-radius:8px;font-size:12px}}
.product-body{{padding:15px;display:flex;flex-direction:column;flex:1}}.badges{{display:flex;justify-content:space-between;gap:8px}}.badge{{font-size:11px;color:var(--blue);background:#1c2b47;padding:5px 7px;border-radius:7px}}.badge.hot{{color:#ff9f90;background:#3c2425}}.badge.available{{color:var(--green)}}.badge.unavailable{{color:var(--hot)}}.badge.unknown{{color:var(--yellow)}}
h3{{font-size:15px;line-height:1.4;min-height:42px}}.price{{font-size:25px;font-weight:800}}.specs{{min-height:40px}}.reason{{color:#ff9f90}}.action{{margin-top:auto;color:#b8c7ff;text-decoration:none;font-weight:700}}.action:hover{{text-decoration:underline}}
.detected{{font-size:12px;margin:2px 0 12px}}.chart-scroll{{overflow-x:auto;padding:8px 0}}.hour-chart{{height:250px;min-width:820px;display:grid;grid-template-columns:repeat(24,1fr);gap:7px;align-items:end;border-bottom:1px solid var(--line)}}.hour{{height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:5px}}.hour strong{{font-size:11px;color:var(--cyan)}}.hour i{{display:block;width:72%;min-height:2px;background:linear-gradient(180deg,var(--cyan),var(--blue));border-radius:6px 6px 0 0}}.hour span{{font-size:10px;color:var(--muted);padding-bottom:7px}}.explain{{padding:12px 14px;border-left:3px solid var(--cyan);background:#102238;color:var(--muted);border-radius:6px}}
.section-head{{display:flex;justify-content:space-between;gap:15px;align-items:center;margin-bottom:14px}}.filters{{display:flex;gap:8px}}input,select{{background:var(--panel);border:1px solid var(--line);color:white;padding:10px;border-radius:10px}}input{{min-width:260px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:12px}}td a{{text-decoration:none}}.down{{color:var(--green)}}.up{{color:var(--hot)}}.empty{{color:var(--muted);padding:22px;text-align:center}}footer{{margin-top:30px;color:var(--muted);font-size:12px}}
@media(max-width:850px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.split{{grid-template-columns:1fr}}header{{align-items:start;flex-direction:column}}.health{{text-align:left}}.section-head{{align-items:stretch;flex-direction:column}}.filters{{flex-direction:column}}input{{min-width:0;width:100%}}.table-wrap{{overflow:auto}}}}
</style></head><body><main>
<header><div><div class="eyebrow">Personal Automation Platform</div><h1>Cash Converters</h1><div class="sub">Surveillance des ordinateurs de bureau · ordre réel du catalogue</div></div>
<div class="health"><strong class="{status_class}">● {_e(status)}</strong><div class="muted">Dernier scan : <time>{_e(last_scan)}</time></div></div></header>
<nav class="tabs" aria-label="Sections">
  <button class="tab active" data-tab="overview">Vue d’ensemble</button>
  <button class="tab" data-tab="offers">Offres <b>{len(offers)}</b></button>
  <button class="tab" data-tab="today">Nouveautés aujourd’hui <b>{len(today)}</b></button>
  <button class="tab" data-tab="latest">100 derniers</button>
  <button class="tab" data-tab="activity">Heures d’ajout</button>
  <button class="tab" data-tab="prices">Prix <b>{len(changes)}</b></button>
  <button class="tab" data-tab="review">À clarifier <b>{len(clarifications)}</b></button>
</nav>
<section class="view active" id="overview">
 <div class="kpis"><div class="kpi"><span>Catalogue suivi</span><strong>{total or len(listings)}</strong></div>
 <div class="kpi"><span>Affichés ici</span><strong>{len(listings)}</strong></div>
 <div class="kpi hot"><span>Offres détectées</span><strong>{len(offers)}</strong></div>
 <div class="kpi"><span>Réservables</span><strong>{len(available)}</strong></div>
 <div class="kpi"><span>Non réservables</span><strong>{len(unavailable)}</strong></div>
 <div class="kpi"><span>Dernière nouveauté détectée</span><strong>{last_discovery_time}</strong><small>{last_discovery_date}</small></div></div>
 <div class="split"><div class="panel"><h2>Plateformes des 100 derniers</h2>{_bars(platforms, len(listings))}</div>
 <div class="panel"><h2>Magasins les plus présents</h2>{_bars(stores, len(listings))}</div></div>
 <div class="section-head" style="margin-top:24px"><h2>Les six derniers PC</h2></div>
 <div class="grid">{''.join(cards[x.external_id] for x in listings[:6])}</div>
</section>
<section class="view" id="offers"><div class="section-head"><div><h2>Offres à examiner</h2><div class="muted">Règles AM4/AM5 actuellement configurées</div></div></div>
 <div class="grid filter-grid">{''.join(cards[x.external_id] for x in offers) or '<p class="empty">Aucune offre détectée parmi les 100 derniers.</p>'}</div></section>
<section class="view" id="today"><div class="section-head"><div><h2>Nouveautés aujourd’hui</h2><div class="muted">Nouveaux ordinateurs réellement découverts aujourd’hui, hors catalogue initial</div></div></div>
 <div class="grid">{discovery_cards or '<p class="empty">Aucun nouvel ordinateur détecté aujourd’hui.</p>'}</div></section>
<section class="view" id="latest"><div class="section-head"><div><h2>100 derniers ordinateurs</h2><div class="muted">#1 correspond au premier produit du site</div></div>
 <div class="filters"><input id="search" placeholder="Rechercher CPU, GPU, magasin…"><select id="availability"><option value="">Toutes disponibilités</option><option value="available">Réservables</option><option value="unavailable">Non réservables</option><option value="unknown">À vérifier</option></select></div></div>
 <div class="grid filter-grid" id="latest-grid">{''.join(cards[x.external_id] for x in listings)}</div></section>
<section class="view" id="activity"><div class="section-head"><div><h2>Heures habituelles des ajouts</h2><div class="muted">Répartition de toutes les nouveautés détectées, heure de Bruxelles</div></div></div>
 <div class="panel"><p class="explain">L’heure affichée est celle de notre détection. Avec un scan toutes les 15 minutes, l’ajout réel sur le site a normalement eu lieu dans les 15 minutes précédentes.</p>{_hour_chart(discoveries)}</div></section>
<section class="view" id="prices"><div class="section-head"><div><h2>Historique des changements de prix</h2><div class="muted">Contrôle périodique des 100 annonces les plus récentes</div></div></div>
 <div class="panel table-wrap"><table><thead><tr><th>Ordinateur</th><th>Avant</th><th>Maintenant</th><th>Évolution</th><th>Détecté</th></tr></thead><tbody>{changed}</tbody></table></div></section>
<section class="view" id="review"><div class="section-head"><div><h2>À clarifier</h2><div class="muted">Informations incomplètes ou ambiguës à corriger via Telegram</div></div></div>
 <div class="grid">{''.join(cards[x.external_id] for x in clarifications) or '<p class="empty">Aucune clarification en attente.</p>'}</div></section>
<footer>{len(analyzed)}/{len(listings)} annonces contiennent déjà des caractéristiques reconnues · {errors} erreur(s) au dernier scan · Page générée {_e(generated)} UTC</footer>
</main><script>
const tabs=[...document.querySelectorAll('.tab')],views=[...document.querySelectorAll('.view')];
function openTab(id){{tabs.forEach(x=>x.classList.toggle('active',x.dataset.tab===id));views.forEach(x=>x.classList.toggle('active',x.id===id));history.replaceState(null,'','#'+id)}}
tabs.forEach(x=>x.addEventListener('click',()=>openTab(x.dataset.tab)));if(location.hash)openTab(location.hash.slice(1));
const search=document.querySelector('#search'),availability=document.querySelector('#availability');
function filter(){{const q=search.value.toLocaleLowerCase();document.querySelectorAll('#latest-grid .product').forEach(x=>{{x.hidden=!x.dataset.search.includes(q)||(availability.value&&x.dataset.availability!==availability.value)}})}}
search.addEventListener('input',filter);availability.addEventListener('change',filter);
</script></body></html>'''
