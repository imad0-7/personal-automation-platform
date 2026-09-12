from __future__ import annotations

import html
import logging
from zoneinfo import ZoneInfo

import httpx

from automation_platform.core.logging import log_event
from automation_platform.core.models import Notification, Priority, RunStatus, RunSummary, utc_now

from .controls import DEFAULTS, poll_commands
from .hardware import analyze_listing
from .parser import ParserFailure
from .scraper import CashConvertersScraper

AUTOMATION_NAME = 'cashconverters'
STATE = 'cashconverters-v2'


class SuspiciousScan(RuntimeError):
    pass


def build_notification(listing, config=None) -> Notification:
    reasons = listing.attributes.get('offer_reasons', [])
    price = f'{listing.price_cents / 100:.2f} €' if listing.price_cents is not None else 'Prix inconnu'
    fields = listing.attributes.get('hardware', {}).get('fields', {})
    specs = [f"{k} : {v['value']} ({v['kind']})" for k, v in fields.items() if k != 'storage']
    state = listing.attributes.get('reservable')
    availability = ('Vite, réservation possible au dernier contrôle.' if state is True else
                    'Dommage, réservation indisponible au dernier contrôle.' if state is False else
                    'Disponibilité non vérifiée.')
    text = '\n'.join([listing.title, price, 'Magasin : ' + (listing.store or 'inconnu'),
                      *specs, *reasons, availability,
                      'Contrôle : ' + str(listing.attributes.get('reservation_checked_at', 'inconnu'))])
    return Notification(title='OFFRE À EXAMINER' if reasons else 'NOUVEL ORDINATEUR',
                        message=html.escape(text), priority=Priority.URGENT if reasons else Priority.NORMAL,
                        url=listing.url, metadata={'external_id': listing.external_id})


class CashConvertersAutomation:
    def __init__(self, repository, scraper, notifier, config):
        self.repository, self.scraper, self.notifier, self.config = repository, scraper, notifier, config
        self.logger = logging.getLogger(__name__)
        self.namespace = 'subscriber:' + str(getattr(notifier, 'chat_id', 'local')) + ':cashconverters'

    def _queue(self, key, notification):
        self.repository.queue_event(AUTOMATION_NAME, self.namespace + ':' + key, notification)

    def _chunks(self, key, title, lines):
        chunk, n = '', 0
        for line in lines:
            if len(chunk) + len(line) > 2200 and chunk:
                self._queue(f'{key}:{n}', Notification(title=title, message=chunk))
                n, chunk = n + 1, ''
            chunk += line + '\n'
        if chunk:
            self._queue(f'{key}:{n}', Notification(title=title, message=chunk))

    def run(self) -> RunSummary:
        repo = self.repository
        summary = RunSummary(automation=AUTOMATION_NAME, started_at=utc_now())
        run_id = repo.begin_run(AUTOMATION_NAME)
        now = summary.started_at
        bucket = str(int(now.timestamp()) // 900)
        try:
            try:
                poll_commands(repo, self.notifier, self.namespace)
            except Exception as exc:  # noqa: BLE001 - commands cannot block monitoring
                summary.errors.append('command_poll: ' + type(exc).__name__)
            prefs = repo.state(self.namespace, 'preferences', DEFAULTS.copy())
            baseline = not repo.state(STATE, 'baseline', False)
            last_price = repo.state(STATE, 'last_price_scan', 0)
            price_snapshot = repo.state(STATE, 'price_snapshot', {})
            price_scan = now.timestamp() - last_price >= 7200
            known = set(repo.state(STATE, 'known_catalog', []))
            if isinstance(self.scraper, CashConvertersScraper):
                listings = self.scraper.collect(full=baseline, price_scan=price_scan, known_ids=known)
            else:
                listings = self.scraper.collect()
            summary.observed = len(listings)
            previous = repo.state(STATE, 'recent_count', 0)
            if (len(listings) < self.config.minimum_products or
                    (not baseline and previous and len(listings) < previous * self.config.sudden_drop_ratio)):
                raise SuspiciousScan('Catalogue vide ou chute anormale')
            ordinary, price_lines = [], []
            review = repo.state(self.namespace, 'review', {})
            budget = self.config.detail_requests_limit
            deferred = repo.state(STATE, 'detail_pending', [])
            ids = {x.external_id for x in listings}
            for ident in deferred:
                old = repo.get_listing('cashconverters', ident)
                if old and ident not in ids:
                    listings.append(old)
            next_deferred = []
            for index, listing in enumerate(listings):
                old = repo.get_listing(listing.source, listing.external_id)
                old_price = price_snapshot.get(listing.external_id, old.price_cents if old else None)
                new = not baseline and listing.external_id not in known and listing.external_id not in deferred
                changed = (not baseline and price_scan and index < 100 and old is not None
                           and old_price is not None and listing.price_cents is not None
                           and old_price != listing.price_cents)
                if old:
                    listing.attributes = {**old.attributes, **listing.attributes}
                needs_detail = new or changed or listing.external_id in deferred or (
                    not baseline and index < 100 and not listing.attributes.get('detail_checked'))
                fresh = False
                if needs_detail and budget > 0:
                    budget -= 1
                    try:
                        self.scraper.enrich(listing)
                        listing.attributes['detail_checked'] = True
                        fresh = True
                    except (ParserFailure, httpx.HTTPError) as exc:
                        summary.errors.append('detail ' + listing.external_id + ': ' + type(exc).__name__)
                if (new or listing.external_id in deferred) and not fresh:
                    next_deferred.append(listing.external_id)
                correction = repo.state(self.namespace, 'correction:' + listing.external_id, {})
                reasons = analyze_listing(listing, correction)
                summary.discovered += int(new)
                event = new or listing.external_id in deferred or changed
                if not baseline and event and reasons and prefs['mode'] != 'pause':
                    event_key = (f'price:{old_price}:{listing.price_cents}:{last_price}'
                                 if changed else 'new')
                    self._queue('offer:' + listing.external_id + ':' + event_key, build_notification(listing))
                elif new and prefs['mode'] == 'tous':
                    self._queue('new:' + listing.external_id, build_notification(listing))
                elif new and prefs['mode'] == 'resume':
                    price = f'{listing.price_cents / 100:.2f} €' if listing.price_cents is not None else '? €'
                    ordinary.append(f'<a href="{html.escape(listing.url, quote=True)}">'
                                    f'{html.escape(listing.title[:200])}</a> — {price}')
                if changed and prefs['mode'] != 'pause':
                    price_lines.append(html.escape(f'{listing.title[:150]} : '
                                       f'{old_price / 100:.2f} → {listing.price_cents / 100:.2f} €\n'
                                       + listing.url))
                questions = listing.attributes['hardware']['questions']
                if not baseline and questions and not correction and (new or fresh):
                    review[listing.external_id] = {'title': listing.title[:150], 'url': listing.url,
                                                   'questions': questions}
                known.add(listing.external_id)
                if index < 100 and (baseline or price_scan or new):
                    price_snapshot[listing.external_id] = listing.price_cents
            if not baseline and prefs['mode'] != 'pause' and (ordinary or price_lines or prefs['reports']):
                self._chunks('report:' + str(run_id), 'COMPTE RENDU CASH CONVERTERS', [
                    f'{summary.observed} PC contrôlés · {summary.discovered} nouveaux',
                    *ordinary, *price_lines, 'Aucune nouveauté.' if not summary.discovered else '',
                ])
            local = now.astimezone(ZoneInfo('Europe/Brussels'))
            day = local.date().isoformat()
            if (local.hour >= 12 and review and prefs['mode'] != 'pause'
                    and repo.state(self.namespace, 'review_day') != day):
                lines = ['À clarifier (maximum 5 cas) :']
                for ident, case in list(review.items())[:5]:
                    lines.append(html.escape(f"ID {ident} — {case['title']}\n"
                                             + ', '.join(case['questions']) + '\n' + case['url']))
                lines.append('/corriger ID ram_gb=32 ram_type=DDR5 (annonce uniquement)')
                self._chunks('review:' + day, 'QUESTIONS MATÉRIEL', lines)
                repo.set_state(self.namespace, 'review_day', day)
            repo.save_listings(listings)
            repo.set_state(self.namespace, 'review', review)
            repo.set_state(STATE, 'detail_pending', next_deferred)
            repo.set_state(STATE, 'known_catalog', sorted(known))
            repo.set_state(STATE, 'price_snapshot', price_snapshot)
            repo.set_state(STATE, 'recent_count', min(summary.observed, 42))
            if price_scan:
                repo.set_state(STATE, 'last_price_scan', now.timestamp())
            if baseline:
                repo.cancel_legacy_notifications(AUTOMATION_NAME)
                repo.set_state(STATE, 'baseline', True)
            incident = repo.state(STATE, 'incident')
            if incident:
                self._queue('recovery:' + incident['id'], Notification(
                    title='SITE RÉTABLI', message='Le catalogue Cash Converters est de nouveau lisible.'))
                repo.set_state(STATE, 'incident', None)
            if summary.errors:
                self._queue('partial:' + bucket, Notification(title='CONTRÔLE PARTIEL',
                    message='Certaines fiches ou commandes n’ont pas pu être lues. Voir GitHub Actions.'))
            summary.status = RunStatus.SUCCESS
        except (ParserFailure, httpx.HTTPError, SuspiciousScan) as exc:
            summary.status = RunStatus.PARSER_FAILURE if isinstance(exc, ParserFailure) else RunStatus.SITE_FAILURE
            summary.errors.append(type(exc).__name__)
            incident = repo.state(STATE, 'incident') or {'id': str(run_id)}
            repo.set_state(STATE, 'incident', incident)
            self._queue('incident:' + incident['id'], Notification(
                title='ALERTE TECHNIQUE CASH CONVERTERS', priority=Priority.URGENT,
                message=f'{summary.status.value} : site inaccessible ou catalogue illisible. '
                        'État précédent conservé. Vérifier les journaux GitHub Actions.',
                url='https://github.com/imad0-7/personal-automation-platform/actions'))
        except Exception as exc:  # noqa: BLE001 - automation boundary records unexpected failures
            summary.status = RunStatus.FAILED
            summary.errors.append(type(exc).__name__)
            self._queue('internal:' + bucket, Notification(
                title='ERREUR DU MONITEUR', message='Échec interne ; consulter GitHub Actions.'))
        try:
            for ident, notification in repo.pending_notifications(AUTOMATION_NAME):
                self.notifier.notify(notification)
                repo.mark_notification_sent(ident, self.notifier.backend_name)
                summary.notifications_sent += 1
        except Exception as exc:  # noqa: BLE001 - preserve outbox when any backend fails
            summary.status = RunStatus.FAILED
            summary.errors.append('notification_delivery: ' + type(exc).__name__)
        summary.requests_count = self.scraper.http.requests_count
        summary.finished_at = utc_now()
        repo.set_state(STATE, 'last_status', {
            'status': summary.status.value, 'finished_at': summary.finished_at.isoformat(),
            'observed': summary.observed, 'new': summary.discovered, 'errors': summary.errors,
        })
        repo.finish_run(run_id, summary)
        log_event(self.logger, logging.INFO, 'automation_completed', status=summary.status.value,
                  observed=summary.observed, discovered=summary.discovered,
                  notifications=summary.notifications_sent)
        return summary
