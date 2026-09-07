"""One-shot operational jobs; schedule these through cron or a queue, not an agent loop."""

from __future__ import annotations

from collections import Counter

from app.application.catalog import Catalog
from app.domain.models import AuditEvent, Freshness, new_id, utc_now
from app.domain.search import freshness_for


def stale_offer_sweep(catalog: Catalog, actor: str = "scheduler") -> dict[str, int]:
    """Report freshness and record a durable audit checkpoint.

    Search already suppresses stale offers at read time. This job makes the
    backlog visible for alerts without mutating the source evidence.
    """
    now = utc_now()
    states = Counter(
        freshness_for(offer, catalog.sources[offer.source_id], now).value
        for offer in catalog.offers.values()
    )
    report = {state.value: states.get(state.value, 0) for state in Freshness}
    catalog.audit_events.append(AuditEvent(
        id=new_id(), actor=actor, action="offers.freshness_swept", entity_type="catalog", entity_id="global",
        before_state={}, after_state=report, occurred_at=now,
    ))
    catalog.persist()
    return report
