"""A pinned product is independent of the desktop catalogue and its refresh budget."""
from __future__ import annotations

import json
import re
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
        if reservable is None:
            raise ParserFailure('Watched reservation control missing')
        if reservable and state.get('reservable') is not True:
            episode = state.get('availability_episode', 0) + 1
            for index in range(1, 5):
                queue(f'watch-available:{url}:{episode}:{index}', Notification(
                    title=f'💰💰💰 DISPONIBLE ({index}/4)',
                    message=title + ' : réservation possible au dernier contrôle. 💰💰💰',
                    priority=Priority.URGENT, url=url))
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
                    'consécutifs. Le suivi de réservation est terminé.', url=url))
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
