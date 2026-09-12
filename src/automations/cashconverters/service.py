from __future__ import annotations

import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from automation_platform.core.database.base import ListingRepository
from automation_platform.core.logging import log_event
from automation_platform.core.models import Notification, Priority, RunStatus, RunSummary, utc_now
from automation_platform.core.notifications.base import Notifier

from .config import CashConvertersConfig
from .parser import ParserFailure
from .scoring import score_listing
from .scraper import CashConvertersScraper

AUTOMATION_NAME = "cashconverters"


class SuspiciousScan(RuntimeError):
    pass


def build_notification(listing, config: CashConvertersConfig) -> Notification:
    price = f"{listing.price_cents / 100:,.2f} €".replace(",", " ") if listing.price_cents is not None else "Prix inconnu"
    detected = datetime.now(ZoneInfo("Europe/Brussels")).strftime("%H:%M")
    reasons = "\n".join(f"• {html.escape(reason)}" for reason in listing.score_reasons)
    message = (
        f"<b>{html.escape(listing.title)}</b>\n"
        f"{price}\n\n"
        f"Magasin : {html.escape(listing.store or 'inconnu')}\n"
        f"Score : {listing.score}/10\n"
        f"Détecté à : {detected}\n\n"
        f"Pourquoi :\n{reasons}"
    )
    priority = Priority.URGENT if listing.score >= config.urgent_min_score else Priority.NORMAL
    return Notification(
        title="NOUVELLE ANNONCE CASH CONVERTERS",
        message=message,
        priority=priority,
        url=listing.url,
        metadata={"external_id": listing.external_id, "score": listing.score},
    )


class CashConvertersAutomation:
    def __init__(
        self,
        repository: ListingRepository,
        scraper: CashConvertersScraper,
        notifier: Notifier,
        config: CashConvertersConfig,
    ):
        self.repository = repository
        self.scraper = scraper
        self.notifier = notifier
        self.config = config
        self.logger = logging.getLogger(__name__)

    def _validate_volume(self, observed: int) -> None:
        if observed < self.config.minimum_products:
            raise SuspiciousScan(f"Only {observed} unique products; minimum is {self.config.minimum_products}")
        previous = self.repository.previous_observed_count(AUTOMATION_NAME)
        if previous and observed < previous * self.config.sudden_drop_ratio:
            raise SuspiciousScan(f"Product count dropped from {previous} to {observed}")

    def run(self) -> RunSummary:
        summary = RunSummary(automation=AUTOMATION_NAME, started_at=utc_now())
        run_id = self.repository.begin_run(AUTOMATION_NAME)
        try:
            listings = self.scraper.collect()
            summary.observed = len(listings)
            self._validate_volume(summary.observed)
            bootstrap = not self.repository.has_successful_run(AUTOMATION_NAME)
            known = self.repository.known_ids("cashconverters", [x.external_id for x in listings])
            new_listings = [x for x in listings if x.external_id not in known]

            if not bootstrap:
                for listing in new_listings[: self.config.detail_requests_limit]:
                    try:
                        self.scraper.enrich(listing)
                    except (ParserFailure, httpx.HTTPError) as exc:
                        summary.errors.append(f"detail {listing.external_id}: {exc}")
                for listing in new_listings:
                    score_listing(listing, self.config)

            self.repository.save_listings(listings)
            summary.discovered = 0 if bootstrap else len(new_listings)
            if not bootstrap:
                for listing in new_listings:
                    if listing.score >= self.config.notify_min_score:
                        self.repository.enqueue_notification(
                            AUTOMATION_NAME, listing, build_notification(listing, self.config)
                        )

            for notification_id, notification in self.repository.pending_notifications(AUTOMATION_NAME):
                self.notifier.notify(notification)
                self.repository.mark_notification_sent(notification_id, self.notifier.backend_name)
                summary.notifications_sent += 1

            summary.status = RunStatus.SUCCESS
            log_event(self.logger, logging.INFO, "automation_completed", bootstrap=bootstrap,
                      observed=summary.observed, discovered=summary.discovered,
                      notifications=summary.notifications_sent)
        except ParserFailure as exc:
            summary.status = RunStatus.PARSER_FAILURE
            summary.errors.append(str(exc))
            log_event(self.logger, logging.ERROR, "parser_failure", error=str(exc))
        except (httpx.HTTPError, SuspiciousScan) as exc:
            summary.status = RunStatus.SITE_FAILURE
            summary.errors.append(str(exc))
            log_event(self.logger, logging.ERROR, "site_failure", error=str(exc))
        except Exception as exc:
            summary.status = RunStatus.FAILED
            summary.errors.append(str(exc))
            self.logger.exception("automation_failed")
        finally:
            summary.requests_count = self.scraper.http.requests_count
            summary.finished_at = utc_now()
            self.repository.finish_run(run_id, summary)
        return summary
