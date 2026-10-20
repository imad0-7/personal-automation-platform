from __future__ import annotations

import html
import json
from collections import Counter
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BRUSSELS = ZoneInfo('Europe/Brussels')
MONTHS_FR = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin',
             'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre')


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_scan_time(value: object) -> str:
    if not isinstance(value, str):
        return 'Pas encore de scan'
    try:
        local = datetime.fromisoformat(value).astimezone(BRUSSELS)
    except ValueError:
        return value
    return f'{local.day} {MONTHS_FR[local.month - 1]} {local.year} à {local:%H:%M}'


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
    activity_rows = repo.scan_activity('cashconverters')
    activity_data = []
    for row in activity_rows:
        local = datetime.fromisoformat(row['observed_at']).astimezone(BRUSSELS)
        activity_data.append({
            'ts': datetime.fromisoformat(row['observed_at']).isoformat(),
            'date': local.date().isoformat(),
            'dow': local.weekday(),
            'hour': local.hour,
            'added': int(row['added_count']),
            'removed': int(row['removed_count']),
            'total': int(row['total_count']),
        })
    activity_json = json.dumps(activity_data, separators=(',', ':'))
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
    last_scan = _format_scan_time(state.get('finished_at'))
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
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}.product{{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;min-width:0}}.product[hidden]{{display:none!important}}.product.offer{{border-color:#a5534b;box-shadow:0 0 0 1px #6e3732}}
.visual{{aspect-ratio:16/9;background:#0c1527;position:relative;display:grid;place-items:center;overflow:hidden}}.visual img{{width:100%;height:100%;object-fit:cover;display:block}}.no-image{{font-size:32px;color:#344762}}.rank{{position:absolute;top:10px;right:10px;background:#07101dcc;padding:5px 8px;border-radius:8px;font-size:12px}}
.product-body{{padding:15px;display:flex;flex-direction:column;flex:1}}.badges{{display:flex;justify-content:space-between;gap:8px}}.badge{{font-size:11px;color:var(--blue);background:#1c2b47;padding:5px 7px;border-radius:7px}}.badge.hot{{color:#ff9f90;background:#3c2425}}.badge.available{{color:var(--green)}}.badge.unavailable{{color:var(--hot)}}.badge.unknown{{color:var(--yellow)}}
h3{{font-size:15px;line-height:1.4;min-height:42px}}.price{{font-size:25px;font-weight:800}}.specs{{min-height:40px}}.reason{{color:#ff9f90}}.action{{margin-top:auto;color:#b8c7ff;text-decoration:none;font-weight:700}}.action:hover{{text-decoration:underline}}
.detected{{font-size:12px;margin:2px 0 12px}}.chart-scroll,.heatmap-scroll{{overflow-x:auto;padding:8px 0}}.activity-summary{{padding:12px 14px;margin:14px 0;background:#0d1a2d;border:1px solid var(--line);border-radius:10px;color:var(--text)}}.activity-title{{margin:20px 0 8px!important}}.activity-heatmap{{min-width:860px;display:grid;grid-template-columns:52px repeat(24,1fr);gap:4px;align-items:center}}.hm-label{{font-size:10px;color:var(--muted);text-align:center}}.hm-day{{text-align:left;font-size:11px;color:var(--muted)}}.hm-cell{{height:28px;border-radius:5px;background:#17243b;border:1px solid #223551;display:flex;align-items:center;justify-content:center;font-size:9px;color:#dfe8ff}}.hm-cell.medium{{background:#334362}}.hm-cell.high{{background:#4b5670}}.hm-cell.no-data{{color:#53627c;background:#10192a}}.activity-hours{{height:230px;min-width:860px;display:grid;grid-template-columns:repeat(24,1fr);gap:6px;align-items:end;border-bottom:1px solid var(--line)}}.activity-hour{{height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px}}.activity-hour strong{{font-size:10px}}.activity-hour i{{display:block;width:72%;min-height:2px;border-radius:5px 5px 0 0;background:#34445f}}.activity-hour.medium i{{background:#50607d}}.activity-hour.high i{{background:#71809c}}.activity-hour span{{font-size:9px;color:var(--muted);padding-bottom:5px}}.activity-legend{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-top:12px}}.activity-legend span{{display:flex;align-items:center;gap:6px}}.level{{width:12px;height:12px;border-radius:3px;background:#34445f}}.level.medium{{background:#50607d}}.level.high{{background:#71809c}}.hour-chart{{height:250px;min-width:820px;display:grid;grid-template-columns:repeat(24,1fr);gap:7px;align-items:end;border-bottom:1px solid var(--line)}}.hour{{height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:5px}}.hour strong{{font-size:11px;color:var(--cyan)}}.hour i{{display:block;width:72%;min-height:2px;background:linear-gradient(180deg,var(--cyan),var(--blue));border-radius:6px 6px 0 0}}.hour span{{font-size:10px;color:var(--muted);padding-bottom:7px}}.explain{{padding:12px 14px;border-left:3px solid var(--cyan);background:#102238;color:var(--muted);border-radius:6px}}
.section-head{{display:flex;justify-content:space-between;gap:15px;align-items:center;margin-bottom:14px}}.filters{{display:flex;gap:8px}}input,select,.period{{background:var(--panel);border:1px solid var(--line);color:white;padding:10px;border-radius:10px}}.period{{cursor:pointer;color:var(--muted)}}.period.active{{color:white;background:#253b67;border-color:#4162a4}}input{{min-width:260px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:12px}}td a{{text-decoration:none}}.down{{color:var(--green)}}.up{{color:var(--hot)}}.empty{{color:var(--muted);padding:22px;text-align:center}}footer{{margin-top:30px;color:var(--muted);font-size:12px}}
@media(max-width:850px){{main{{padding:22px 12px 48px}}.kpis{{grid-template-columns:repeat(2,1fr)}}.split{{grid-template-columns:1fr}}header{{align-items:start;flex-direction:column}}.health{{text-align:left}}.section-head{{align-items:stretch;flex-direction:column}}.filters{{flex-direction:column}}input{{min-width:0;width:100%}}.table-wrap{{overflow:auto}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}.visual{{aspect-ratio:4/3}}.product{{border-radius:12px}}.product-body{{padding:10px}}.badges{{gap:4px;align-items:flex-start;flex-wrap:wrap}}.badge{{font-size:9px;padding:4px 5px}}h3{{font-size:12px;line-height:1.3;min-height:0;margin:10px 0 8px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.price{{font-size:20px}}.specs{{font-size:11px;line-height:1.35;min-height:0;margin:9px 0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.store,.detected,.reason{{font-size:10px;margin:6px 0}}.action{{font-size:11px;margin-top:8px}}.rank{{top:6px;right:6px;padding:4px 6px;font-size:10px}}}}
</style></head><body><main>
<header><div><div class="eyebrow">Personal Automation Platform</div><h1>Cash Converters</h1><div class="sub">Surveillance des ordinateurs de bureau · ordre réel du catalogue</div></div>
<div class="health"><strong class="{status_class}">● {_e(status)}</strong><div class="muted">Dernier scan : <time>{_e(last_scan)}</time></div></div></header>
<nav class="tabs" aria-label="Sections">
  <button class="tab active" data-tab="overview">Vue d’ensemble</button>
  <button class="tab" data-tab="offers">Offres <b>{len(offers)}</b></button>
  <button class="tab" data-tab="today">Nouveautés aujourd’hui <b>{len(today)}</b></button>
  <button class="tab" data-tab="latest">100 derniers</button>
  <button class="tab" data-tab="activity">Activité</button>
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
<section class="view" id="offers"><div class="section-head"><div><h2>Offres à examiner</h2><div class="muted">Règles AM4/AM5 actuellement configurées · <span id="offer-count">{len(offers)}</span> affichée(s)</div></div>
 <div class="filters"><input id="offer-search" placeholder="Rechercher CPU, GPU, magasin…"><select id="offer-availability"><option value="">Toutes disponibilités</option><option value="available">Réservables</option><option value="unavailable">Non réservables</option><option value="unknown">À vérifier</option></select><select id="offer-platform"><option value="">Toutes plateformes</option><option value="AM4">AM4</option><option value="AM5">AM5</option><option value="Inconnu">Inconnu</option></select></div></div>
 <div class="grid filter-grid" id="offers-grid">{''.join(cards[x.external_id] for x in offers) or '<p class="empty">Aucune offre détectée parmi les 100 derniers.</p>'}</div></section>
<section class="view" id="today"><div class="section-head"><div><h2>Nouveautés aujourd’hui</h2><div class="muted">Nouveaux ordinateurs réellement découverts aujourd’hui, hors catalogue initial</div></div></div>
 <div class="grid">{discovery_cards or '<p class="empty">Aucun nouvel ordinateur détecté aujourd’hui.</p>'}</div></section>
<section class="view" id="latest"><div class="section-head"><div><h2>100 derniers ordinateurs</h2><div class="muted">#1 correspond au premier produit du site</div></div>
 <div class="filters"><input id="search" placeholder="Rechercher CPU, GPU, magasin…"><select id="availability"><option value="">Toutes disponibilités</option><option value="available">Réservables</option><option value="unavailable">Non réservables</option><option value="unknown">À vérifier</option></select></div></div>
 <div class="grid filter-grid" id="latest-grid">{''.join(cards[x.external_id] for x in listings)}</div></section>
<section class="view" id="activity"><div class="section-head"><div><h2>Activité du catalogue</h2><div class="muted">Ajouts + disparitions détectés entre deux scans valides · heure de Bruxelles</div></div>
 <div class="filters activity-periods"><button class="period active" data-days="7">7 j</button><button class="period" data-days="30">30 j</button><button class="period" data-days="90">90 j</button><button class="period" data-days="all">Tout</button></div></div>
 <div class="panel"><p class="explain">Une heure est active dès qu’au moins une annonce est ajoutée ou disparaît, même si le total du catalogue reste identique. La fréquence proposée est seulement indicative et ne modifie pas le scanner.</p>
 <div class="activity-summary" id="activity-summary">Calcul de l’activité…</div>
 <h2 class="activity-title">Heatmap jour × heure</h2><div class="heatmap-scroll"><div id="activity-heatmap" class="activity-heatmap"></div></div>
 <h2 class="activity-title">Taux d’activité par heure</h2><div class="chart-scroll"><div id="activity-hours" class="activity-hours"></div></div>
 <div class="activity-legend"><span><i class="level low"></i> faible → 60 min</span><span><i class="level medium"></i> moyenne → 30 min</span><span><i class="level high"></i> forte → 15 min</span></div>
 </div></section>
<section class="view" id="prices"><div class="section-head"><div><h2>Historique des changements de prix</h2><div class="muted">Contrôle périodique des 100 annonces les plus récentes</div></div></div>
 <div class="panel table-wrap"><table><thead><tr><th>Ordinateur</th><th>Avant</th><th>Maintenant</th><th>Évolution</th><th>Détecté</th></tr></thead><tbody>{changed}</tbody></table></div></section>
<section class="view" id="review"><div class="section-head"><div><h2>À clarifier</h2><div class="muted">Informations incomplètes ou ambiguës à corriger via Telegram</div></div></div>
 <div class="grid">{''.join(cards[x.external_id] for x in clarifications) or '<p class="empty">Aucune clarification en attente.</p>'}</div></section>
<footer>{len(analyzed)}/{len(listings)} annonces contiennent déjà des caractéristiques reconnues · {errors} erreur(s) au dernier scan · Page générée {_e(generated)} UTC</footer>
</main><script>
const tabs=[...document.querySelectorAll('.tab')],views=[...document.querySelectorAll('.view')];
function openTab(id){{tabs.forEach(x=>x.classList.toggle('active',x.dataset.tab===id));views.forEach(x=>x.classList.toggle('active',x.id===id));history.replaceState(null,'','#'+id)}}
tabs.forEach(x=>x.addEventListener('click',()=>openTab(x.dataset.tab)));if(location.hash)openTab(location.hash.slice(1));
function setupFilters(gridSelector, searchSelector, availabilitySelector, platformSelector=null, countSelector=null){{
  const grid=document.querySelector(gridSelector),search=document.querySelector(searchSelector),availability=document.querySelector(availabilitySelector);
  const platform=platformSelector?document.querySelector(platformSelector):null,count=countSelector?document.querySelector(countSelector):null;
  if(!grid||!search||!availability)return;
  function apply(){{
    const q=search.value.toLocaleLowerCase(),availabilityValue=availability.value,platformValue=platform?platform.value:'';
    let visible=0;
    grid.querySelectorAll('.product').forEach(x=>{{
      const show=x.dataset.search.includes(q)&&(!availabilityValue||x.dataset.availability===availabilityValue)&&(!platformValue||x.dataset.platform===platformValue);
      x.hidden=!show;if(show)visible+=1;
    }});
    if(count)count.textContent=visible;
  }}
  search.addEventListener('input',apply);availability.addEventListener('change',apply);if(platform)platform.addEventListener('change',apply);apply();
}}
setupFilters('#latest-grid','#search','#availability');
setupFilters('#offers-grid','#offer-search','#offer-availability','#offer-platform','#offer-count');

const activityData={activity_json};
const dayNames=['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
function activityLevel(rate,samples){{
  if(samples<3)return ['no-data','—'];
  if(rate>=0.5)return ['high','15 min'];
  if(rate>=0.2)return ['medium','30 min'];
  return ['low','60 min'];
}}
function renderActivity(days){{
  const now=Date.now(),cutoff=days==='all'?0:now-Number(days)*86400000;
  const rows=activityData.filter(r=>Date.parse(r.ts)>=cutoff);
  const buckets=new Map();
  rows.forEach(r=>{{
    const key=r.date+'-'+r.hour;
    const b=buckets.get(key)||{{date:r.date,dow:r.dow,hour:r.hour,changes:0,scans:0}};
    b.changes+=r.added+r.removed;b.scans+=1;buckets.set(key,b);
  }});
  const hourly=Array.from({{length:24}},()=>({{seen:0,active:0,changes:0}}));
  const matrix=Array.from({{length:7}},()=>Array.from({{length:24}},()=>({{seen:0,active:0,changes:0}})));
  buckets.forEach(b=>{{
    hourly[b.hour].seen++;hourly[b.hour].changes+=b.changes;if(b.changes>0)hourly[b.hour].active++;
    const cell=matrix[b.dow][b.hour];cell.seen++;cell.changes+=b.changes;if(b.changes>0)cell.active++;
  }});
  const heat=document.querySelector('#activity-heatmap');
  let h='<div></div>'+Array.from({{length:24}},(_,i)=>'<div class="hm-label">'+String(i).padStart(2,'0')+'h</div>').join('');
  matrix.forEach((day,di)=>{{
    h+='<div class="hm-day">'+dayNames[di]+'</div>';
    day.forEach(cell=>{{
      const rate=cell.seen?cell.active/cell.seen:0,[level,rec]=activityLevel(rate,cell.seen);
      const pct=cell.seen?Math.round(rate*100):0;
      h+='<div class="hm-cell '+level+'" title="'+dayNames[di]+' · '+pct+'% actifs · '+cell.changes+' changement(s) · '+cell.seen+' heure(s) observée(s)">'+(cell.seen?pct+'%':'·')+'</div>';
    }});
  }});
  heat.innerHTML=h;
  const hours=document.querySelector('#activity-hours');
  hours.innerHTML=hourly.map((x,i)=>{{
    const rate=x.seen?x.active/x.seen:0,[level,rec]=activityLevel(rate,x.seen),pct=x.seen?Math.round(rate*100):0;
    return '<div class="activity-hour '+level+'" title="'+String(i).padStart(2,'0')+'h · '+pct+'% actifs · '+x.changes+' changements · recommandation '+rec+'"><strong>'+(x.seen?pct+'%':'—')+'</strong><i style="height:'+Math.max(2,pct)+'%"></i><span>'+String(i).padStart(2,'0')+'h<br>'+rec+'</span></div>';
  }}).join('');
  const reliable=hourly.filter(x=>x.seen>=3);
  const high=hourly.map((x,i)=>({{...x,hour:i,rate:x.seen?x.active/x.seen:0}})).filter(x=>x.seen>=3&&x.rate>=0.5).map(x=>String(x.hour).padStart(2,'0')+'h');
  const changes=rows.reduce((n,r)=>n+r.added+r.removed,0);
  document.querySelector('#activity-summary').textContent=rows.length
    ? rows.length+' scans · '+changes+' changements détectés · créneaux forte activité : '+(high.join(', ')||'aucun avec assez de recul')
    : 'Pas encore assez de données depuis l’activation du suivi d’activité.';
}}
document.querySelectorAll('.period').forEach(btn=>btn.addEventListener('click',()=>{{
  document.querySelectorAll('.period').forEach(x=>x.classList.toggle('active',x===btn));renderActivity(btn.dataset.days);
}}));
renderActivity('7');
</script></body></html>'''
