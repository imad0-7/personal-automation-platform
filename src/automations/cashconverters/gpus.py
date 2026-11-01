"""Discover standalone target GPUs without mixing them into desktop PC rules."""
from __future__ import annotations

import html
import re
from dataclasses import replace

from automation_platform.core.models import Notification, utc_now

from .scraper import CashConvertersScraper

GPU_STATE = 'cashconverters-gpus-v1'


def gpu_model(listing, models):
    text = listing.title + ' ' + listing.url.rsplit('/', 1)[-1]
    text = re.sub(r'(RTX|GeForce)(?=\d)', r'\1 ', text.replace('-', ' '), flags=re.IGNORECASE)
    # Some GPUs are misfiled (for example under PDA); reject computer categories
    # but do not require a GPU category when the product wording identifies a card.
    if listing.category and 'ordinateur' in listing.category:
        return None
    if re.search(r'\b(portable|laptop|notebook|ordinateur|tour|pc|support|waterblock|cable|câble|bo[iî]te|bo[iî]tier|enclosure|backplate)\b',
                 text, re.IGNORECASE):
        return None
    if re.search(r'\b(?:ryzen|core\s*i[3579]|i[3579]\s*\d{4,5})\b', text, re.IGNORECASE):
        return None
    match = re.search(r'\b(' + '|'.join(re.escape(x) for x in models) + r')(?!\d)\s*(TI\s*SUPER|SUPER|TI)?',
                      text, re.IGNORECASE)
    if (not match or match[1] not in models
            or not re.search(r'rtx|geforce|gpu|carte.*gr.phique', text, re.IGNORECASE)):
        return None
    return 'RTX ' + match[1] + (' ' + match[2].upper() if match[2] else '')


def discover_gpus(repo, http, config, namespace, queue, scraper=None):
    known = set(repo.state(GPU_STATE, 'known', []))
    baseline = not repo.state(GPU_STATE, 'baseline', False)
    last_full = repo.state(GPU_STATE, 'last_full', 0)
    full = baseline or utc_now().timestamp() - last_full >= config.refresh_minutes * 60
    if scraper is None:
        # Each feed has its own verifiable total; deduplicate after collecting both.
        by_id = {}
        for feed in config.gpu_sources:
            source_scraper = CashConvertersScraper(http, replace(config, sources=(feed,)))
            for listing in source_scraper.collect(full=full, known_ids=known):
                by_id[listing.external_id] = listing
        listings = list(by_id.values())
    else:
        listings = scraper.collect(full=full, known_ids=known)
    watches = repo.state(namespace, 'watches', {})
    ignored = set(repo.state(namespace, 'gpu_ignored', []))
    for listing in listings:
        ident = listing.external_id
        model = gpu_model(listing, config.gpu_models)
        if model and ident not in known and ident not in ignored:
            item = watches.setdefault(ident, {'url': listing.url, 'title': listing.title[:120],
                                              'origin': 'gpu', 'burst': False, 'prefix': False,
                                              'silent_initial': baseline})
            if not item.get('reservation', True):
                item.update(origin='gpu', burst=False, prefix=False)
            item.update(price=True, reservation=True)
            if not baseline:
                price = f'{listing.price_cents / 100:.2f} €' if listing.price_cents is not None else '? €'
                vram = re.search(r'\b(8|10|12|16|20|24|32)\s*(?:GB|GO)\b', listing.title, re.IGNORECASE)
                availability = listing.attributes.get('reservable')
                status = ('Non réservé' if availability is True else 'Réservé' if availability is False
                          else 'État de réservation non vérifié')
                text = (f'{model}' + (f' · {vram[1]} Go' if vram else '')
                        + f'\n{listing.title}\n{price}\nMagasin : {listing.store or "inconnu"}\n{status}')
                queue('gpu-new:' + ident, Notification(title='NOUVELLE CARTE GRAPHIQUE',
                      message=html.escape(text), url=listing.url, metadata={'watch_url': listing.url}))
        known.add(ident)
    repo.set_state(namespace, 'watches', watches)
    repo.set_state(GPU_STATE, 'known', sorted(known))
    repo.set_state(GPU_STATE, 'baseline', True)
    if full:
        repo.set_state(GPU_STATE, 'last_full', utc_now().timestamp())
