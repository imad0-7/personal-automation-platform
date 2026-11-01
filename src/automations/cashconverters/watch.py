"""Persistent product watches shared by manual lists and GPU discovery."""
from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from automation_platform.core.models import Listing, Notification, Priority, utc_now

from .parser import ParserFailure, enrich_from_detail

WATCH_STATE = 'cashconverters-watch'
MAX_WATCHES = 5
MAX_PRICE_WATCHES = 20


def refresh_watch(repo, http, config, queue, policy=None) -> str | None:
    policy = policy or {}
    url, title = config.watched_url, config.watched_title
    state = repo.state(WATCH_STATE, url, {})
    if state.get('removed'):
        return None

    def event(kind, title, message, *, final=False, urgent=False):
        state['sequence'] = state.get('sequence', 0) + 1
        queue(f'watch-{kind}:{url}:{state["sequence"]}', Notification(
            title=title, message=html.escape(message), url=url,
            priority=Priority.URGENT if urgent else Priority.NORMAL,
            metadata={'watch_url': url, 'watch_final': final}))

    try:
        page = http.get_text(url, timeout=12, attempts=1)
        _, ident = watch_url(url)
        node = BeautifulSoup(page, 'html.parser').select_one('#product-details[data-product]')
        data = json.loads(node['data-product']) if node else {}
        if str(data.get('id_product')) != ident:
            raise ParserFailure('Watched product identity missing or changed')
        listing = enrich_from_detail(Listing('cashconverters', ident, title, url), page)
        reservable = listing.attributes.get('reservable')
        title = listing.title[:120]
        old_price = state.get('price_cents')
        if (policy.get('price') and old_price is not None and listing.price_cents is not None
                and old_price != listing.price_cents):
            event('price', 'CHANGEMENT DE PRIX',
                  f'{title}\n{old_price / 100:.2f} → {listing.price_cents / 100:.2f} €')
        if listing.price_cents is not None:
            state['price_cents'] = listing.price_cents
        if policy.get('reservation', True) and reservable is not None:
            previous = state.get('reservable')
            if reservable and previous is not True and not policy.get('silent_initial'):
                count = 4 if policy.get('burst', True) else 1
                # Automatic cards alert only on return to availability; discovery has its own alert.
                if policy.get('burst', True) or policy.get('origin') != 'gpu' or previous is False:
                    for index in range(1, count + 1):
                        event('available', f'💰💰💰 DISPONIBLE ({index}/{count})',
                              title + ' : réservation possible au dernier contrôle. 💰💰💰', urgent=True)
            if previous is True and reservable is False:
                event('reserved', 'ARTICLE RÉSERVÉ', title + ' est maintenant réservé.')
            state['reservable'] = reservable
        state.update(title=title, checked_at=utc_now().isoformat(), missing=0)
        if reservable is None and policy.get('reservation', True):
            raise ParserFailure('Watched reservation control missing')
        repo.set_state(WATCH_STATE, url, state)
        if not policy.get('reservation', True):
            return None
        return ('Non réservé' if reservable else 'Réservé') + ' — ' + title
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 410}:
            state['missing'] = state.get('missing', 0) + 1
            if state['missing'] >= 2:
                state['removed'] = True
                event('removed', 'ARTICLE DISPARU — SUIVI SUPPRIMÉ',
                      title + ' : fiche introuvable lors de deux scans consécutifs. '
                      'L’article est retiré de vos suivis.', final=True)
                repo.set_state(WATCH_STATE, url, state)
                return 'Article disparu — ' + title
        else:
            state['missing'] = 0
    except (httpx.HTTPError, ParserFailure, ValueError, TypeError, AttributeError, KeyError):
        state['missing'] = 0
    repo.set_state(WATCH_STATE, url, state)
    suffix = ''
    if state.get('reservable') is not None:
        suffix = (' · dernier état : ' + ('Non réservé' if state['reservable'] else 'Réservé')
                  + ' (' + state['checked_at'] + ')')
    return 'État non vérifié — ' + title + suffix


def watch_url(value: str) -> tuple[str, str]:
    parts = urlsplit(value)
    match = re.fullmatch(r'/fr/[a-z0-9-]+/(\d+)-[a-z0-9-]+\.html', parts.path)
    if parts.scheme != 'https' or parts.netloc != 'www.cashconverters.be' or not match:
        raise ValueError('Lien produit Cash Converters Belgique invalide.')
    return 'https://www.cashconverters.be' + parts.path, match.group(1)


def watch_command(repo, namespace: str, text: str) -> str:
    watches = repo.state(namespace, 'watches', {})
    args = text.split()
    command = args[0]
    if command in {'/suivis', '/prix', '/gpus'} and len(args) == 1:
        selected = {k: v for k, v in watches.items() if (
            command == '/suivis' or command == '/prix' and v.get('price')
            or command == '/gpus' and v.get('origin') == 'gpu')}
        if not selected:
            return 'Aucun article suivi dans cette liste. Ajouter : /suivre LIEN ou /prix LIEN'
        lines = []
        for ident, item in selected.items():
            state = repo.state(WATCH_STATE, item['url'], {})
            status = ('non réservé' if state.get('reservable') is True else
                      'réservé' if state.get('reservable') is False else 'réservation non vérifiée')
            price = state.get('price_cents')
            price_text = f'{price / 100:.2f} €' if price is not None else 'prix à vérifier'
            lines.append(f"{ident} — {state.get('title', item['title'])[:90]}\n"
                         f"{price_text} · {status}\n{item['url']}")
        return '\n\n'.join(lines) + '\nArrêter : /arreter ID'
    if command == '/arreter' and len(args) == 2:
        if watches.pop(args[1], None) is None:
            return 'Cet identifiant ne figure pas dans vos suivis.'
        ignored = set(repo.state(namespace, 'gpu_ignored', []))
        ignored.add(args[1])
        repo.set_state(namespace, 'gpu_ignored', sorted(ignored))
        repo.set_state(namespace, 'watches', watches)
        return 'Suivi arrêté pour ' + args[1] + '.'
    if command not in {'/suivre', '/prix'} or len(args) < 2:
        return 'Commandes : /suivre LIEN · /prix LIEN [LIEN…] · /prix · /suivis · /arreter ID'
    # Validate the entire list before adding anything.
    try:
        products = dict(watch_url(value) for value in args[1:])
    except ValueError as exc:
        return str(exc)
    reservation = command == '/suivre'
    candidates = {ident for ident, item in watches.items() if (
        item.get('price', False) and item.get('origin') != 'gpu' if not reservation else
        item.get('reservation', True) and item.get('burst', True))}
    requested = {ident for ident in products.values()
                 if reservation or watches.get(ident, {}).get('origin') != 'gpu'}
    if len(candidates | requested) > (MAX_WATCHES if reservation else MAX_PRICE_WATCHES):
        return ('Maximum cinq articles en réservation.' if reservation else
                'Maximum vingt articles en suivi de prix.') + ' Arrêter un suivi avec /arreter ID.'
    answers = []
    for url, ident in products.items():
        existing = watches.get(ident)
        field = 'reservation' if reservation else 'price'
        if (existing and existing.get(field, field == 'reservation')
                and (not reservation or existing.get('burst', True))):
            answers.append('Cet article est déjà suivi : ' + ident)
            continue
        title = urlsplit(url).path.rsplit('/', 1)[-1].split('-', 1)[1][:-5].replace('-', ' ')[:120]
        item = existing or {'url': url, 'title': title, 'reservation': False, 'price': False}
        item[field] = True
        if reservation:
            item.update(burst=True, prefix=True)
        watches[ident] = item
        state = repo.state(WATCH_STATE, url, {})
        if reservation and existing and existing.get('origin') == 'gpu':
            state.pop('reservable', None)
        if not existing:
            state.pop('reservable', None)
            state.pop('price_cents', None)
        state.update(removed=False, missing=0)
        repo.set_state(WATCH_STATE, url, state)
        answers.append('Suivi ajouté : ' + ident)
    repo.set_state(namespace, 'watches', watches)
    return '\n'.join(answers) + '. Contrôle à chaque scan (~15 min). /suivis pour consulter.'


def refresh_watches(repo, http, config, namespace, queue) -> str | None:
    watches = repo.state(namespace, 'watches', {})
    lines = []
    for ident, item in list(watches.items()):
        state = repo.state(WATCH_STATE, item['url'], {})
        current = replace(config, watched_url=item['url'],
                          watched_title=state.get('title', item['title']))
        prefix = refresh_watch(repo, http, current, queue, item)
        state = repo.state(WATCH_STATE, item['url'], {})
        if state.get('removed'):
            del watches[ident]
        else:
            if state.get('checked_at'):
                item.pop('silent_initial', None)
            if prefix and item.get('prefix', item.get('origin') != 'gpu' and item.get('reservation', True)):
                lines.append(prefix)
    repo.set_state(namespace, 'watches', watches)
    return '\n'.join(lines) or None
