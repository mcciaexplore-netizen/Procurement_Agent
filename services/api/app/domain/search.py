from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .models import Freshness, Offer, PriceStatus, Product, Source
from .normalization import normalize_mpn


TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class RankedOffer:
    offer: Offer
    score: float
    reasons: tuple[str, ...]
    freshness: Freshness


def freshness_for(offer: Offer, source: Source, now: datetime) -> Freshness:
    if source.status.value != "active":
        return Freshness.SOURCE_UNAVAILABLE
    if not source.policy:
        return Freshness.SOURCE_UNAVAILABLE
    age_hours = (now - offer.observed_at).total_seconds() / 3600
    if age_hours <= source.policy.freshness_sla_hours:
        return Freshness.FRESH
    if age_hours <= source.policy.freshness_sla_hours * 2:
        return Freshness.AGING
    return Freshness.STALE


def _tokens(value: str) -> set[str]:
    return set(TOKEN.findall(value.lower()))


def rank_offers(
    query: str,
    products: dict[str, Product],
    offers: list[Offer],
    sources: dict[str, Source],
    now: datetime,
    quantity: int | None = None,
) -> list[RankedOffer]:
    normalized_query = normalize_mpn(query)
    query_tokens = _tokens(query)
    ranked: list[RankedOffer] = []
    for offer in offers:
        source = sources[offer.source_id]
        freshness = freshness_for(offer, source, now)
        if source.status.value != "active" or freshness is Freshness.STALE:
            continue
        product = products[offer.product_id]
        reasons: list[str] = []
        score = 0.0
        if product.mpn and product.mpn == normalized_query:
            score += 0.35
            reasons.append("exact MPN match")
        else:
            searchable = _tokens(" ".join(filter(None, [product.normalized_name, offer.title, product.manufacturer])))
            overlap = len(query_tokens & searchable)
            if overlap:
                score += min(0.25, overlap * 0.08)
                reasons.append("title/specification token match")
        if score == 0:
            continue
        if freshness is Freshness.FRESH:
            score += 0.10
            reasons.append("within source freshness SLA")
        else:
            score += 0.04
            reasons.append("aging source observation")
        if offer.availability and offer.availability.lower() not in {"unknown", "out of stock"}:
            score += 0.10
            reasons.append("availability evidence")
        if offer.price_status is PriceStatus.PUBLIC and offer.unit and (not quantity or not offer.moq or quantity >= offer.moq):
            score += 0.10
            reasons.append("public price with compatible quantity")
        if source.policy and source.policy.approved:
            score += 0.10
            reasons.append("approved source policy")
        ranked.append(RankedOffer(offer, score, tuple(reasons), freshness))
    return sorted(ranked, key=lambda item: (-item.score, item.offer.price or Decimal("999999999"), item.offer.observed_at), reverse=False)


def group_by_product(ranked: list[RankedOffer]) -> dict[str, list[RankedOffer]]:
    groups: dict[str, list[RankedOffer]] = defaultdict(list)
    for item in ranked:
        groups[item.offer.product_id].append(item)
    return dict(groups)
