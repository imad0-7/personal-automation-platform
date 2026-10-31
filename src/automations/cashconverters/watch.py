"""A pinned product is independent of the desktop catalogue and its refresh budget."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from automation_platform.core.models import Listing, Notification, Priority, utc_now

from .parser import ParserFailure, enrich_from_detail

WATCH_STATE = 'cashconverters-watch'


def refresh_watch(repo, http, config, queue) -> str | None:
    url, title = config.watched_url, config.watched_title
    state = repo.state(WATCH_STATE, url, {})
    if state.get('removed'):
        return None
    try:
        page = http.get_text(url, timeout=12, attempts=1)
        ident = re.match(r'(\d+)-', urlsplit(url).path.rsplit('/', 1)[-1]).group(1)
        node = BeautifulSoup(page, 'html.parser').select_one('#product-details[data-product]')
        data = json.loads(node['data-product']) if node else {}
        if str(data.get('id_product')) != ident:
            raise ParserFailure('Watched product identity missing or changed')
        listing = enrich_from_detail(Listing('cashconverters', ident, title, url), page)
        reservable = listing.attributes.get('reservable')
        title = listing.title[:120]
        state['title'] = title
        if reservable is None:
            raise ParserFailure('Watched reservation control missing')
        if reservable and state.get('reservable') is not True:
            episode = state.get('availability_episode', 0) + 1
            for index in range(1, 5):
                queue(f'watch-available:{url}:{episode}:{index}', Notification(
                    title=f'💰💰💰 DISPONIBLE ({index}/4)',
                    message=title + ' : réservation possible au dernier contrôle. 💰💰💰',
                    priority=Priority.URGENT, url=url, metadata={'watch_url': url}))
            state['availability_episode'] = episode
        state.update(reservable=reservable, checked_at=utc_now().isoformat(), missing=0)
        repo.set_state(WATCH_STATE, url, state)
        return ('Non réservé' if reservable else 'Réservé') + ' — ' + title
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 410}:
            state['missing'] = state.get('missing', 0) + 1
            if state['missing'] >= 2:
                state['removed'] = True
                repo.set_state(WATCH_STATE, url, state)
                queue('watch-removed:' + url, Notification(
                    title='FIN DU SUIVI', message='L’article a disparu du site après deux contrôles '
                    'consécutifs. Le suivi de réservation est terminé.', url=url,
                    metadata={'watch_url': url}))
                return 'Article disparu — ' + title
        else:
            state['missing'] = 0
    except (httpx.HTTPError, ParserFailure, ValueError, TypeError, AttributeError, KeyError):
        # A timeout, a redirect or a changed page must never be mistaken for removal.
        state['missing'] = 0
    repo.set_state(WATCH_STATE, url, state)
    previous = state.get('reservable')
    suffix = ''
    if previous is not None:
        suffix = (' · dernier état : ' + ('Non réservé' if previous else 'Réservé')
                  + ' (' + state['checked_at'] + ')')
    return 'État non vérifié — ' + title + suffix


MAX_WATCHES = 5


def watch_url(value: str) -> tuple[str, str]:
    """Accept only direct HTTPS Cash Converters Belgium product URLs."""
    parts = urlsplit(value)
    match = re.fullmatch(r'/fr/[a-z0-9-]+/(\d+)-[a-z0-9-]+\.html', parts.path)
    if (parts.scheme != 'https' or parts.netloc != 'www.cashconverters.be'
            or not match):
        raise ValueError('Lien produit Cash Converters Belgique invalide.')
    return 'https://www.cashconverters.be' + parts.path, match.group(1)


def watch_command(repo, namespace: str, text: str) -> str:
    watches = repo.state(namespace, 'watches', {})
    args = text.split()
    if args == ['/suivis']:
        if not watches:
            return 'Aucun article suivi. Ajouter : /suivre LIEN'
        lines = []
        for ident, item in watches.items():
            state = repo.state(WATCH_STATE, item['url'], {})
            status = ('disparu' if state.get('removed') else
                      'non réservé' if state.get('reservable') is True else
                      'réservé' if state.get('reservable') is False else 'à vérifier')
            lines.append(f"{ident} — {state.get('title', item['title'])} — {status}\n{item['url']}")
        return '\n\n'.join(lines) + '\nArrêter : /arreter ID'
    if len(args) != 2:
        return 'Commandes : /suivre LIEN · /suivis · /arreter ID'
    if args[0] == '/arreter':
        if watches.pop(args[1], None) is None:
            return 'Cet identifiant ne figure pas dans vos suivis.'
        repo.set_state(namespace, 'watches', watches)
        return 'Suivi arrêté pour ' + args[1] + '.'
    try:
        url, ident = watch_url(args[1])
    except ValueError as exc:
        return str(exc)
    if ident in watches:
        return 'Cet article est déjà suivi : ' + ident
    if len(watches) >= MAX_WATCHES:
        return 'Maximum cinq articles suivis. Arrêter un suivi avec /arreter ID.'
    title = urlsplit(url).path.rsplit('/', 1)[-1].split('-', 1)[1][:-5].replace('-', ' ')
    watches[ident] = {'url': url, 'title': title}
    state = repo.state(WATCH_STATE, url, {})
    state.pop('reservable', None)
    state.update(removed=False, missing=0)
    repo.set_state(WATCH_STATE, url, state)
    repo.set_state(namespace, 'watches', watches)
    return ('Suivi ajouté : ' + ident + '. Contrôle à chaque scan (~15 min). '
            'Quatre alertes 💰 à chaque nouvelle disponibilité. /suivis pour consulter.')


def refresh_watches(repo, http, config, namespace, queue) -> str | None:
    watches = repo.state(namespace, 'watches', {})
    lines = []
    for item in watches.values():
        state = repo.state(WATCH_STATE, item['url'], {})
        current = replace(config, watched_url=item['url'],
                          watched_title=state.get('title', item['title']))
        prefix = refresh_watch(repo, http, current, queue)
        if prefix:
            lines.append(prefix)
    return '\n'.join(lines) or None
