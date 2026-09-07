from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.domain.models import (
    Offer,
    AuditEvent,
    MatchDecision,
    MatchReview,
    OutboundEvent,
    Product,
    PriceStatus,
    RawCapture,
    Source,
    SourcePolicy,
    SourceStatus,
    new_id,
    utc_now,
)
from app.domain.normalization import normalize_listing
from app.domain.policy import assert_outbound_url_allowed, assert_source_can_run
from app.domain.pricing import effective_price
from app.domain.search import freshness_for, group_by_product, rank_offers
from app.application.raw_store import RawCaptureStore, build_raw_capture_store
from app.connectors.csv_feed import parse_csv_feed


class NotFoundError(KeyError):
    pass


class CatalogPersistence(Protocol):
    """Port implemented by durable catalog adapters."""

    def sync(self, catalog: "Catalog") -> None: ...


class Catalog:
    """An adapter-shaped in-memory catalog.

    The API never mutates an offer after import. A later PostgreSQL adapter can
    preserve this contract while storing raw captures in object storage.
    """

    def __init__(self, persistence: CatalogPersistence | None = None, raw_store: RawCaptureStore | None = None) -> None:
        self.sources: dict[str, Source] = {}
        self.captures: dict[str, RawCapture] = {}
        self.products: dict[str, Product] = {}
        self.offers: dict[str, Offer] = {}
        self._external_offer_keys: dict[tuple[str, str], str] = {}
        self._product_keys: dict[tuple[str | None, str | None], str] = {}
        self.outbound_events: list[OutboundEvent] = []
        self.audit_events: list[AuditEvent] = []
        self.match_reviews: dict[str, MatchReview] = {}
        self._persistence = persistence
        self._raw_store = raw_store or build_raw_capture_store()

    def persist(self) -> None:
        if self._persistence:
            self._persistence.sync(self)

    def register_source(self, source: Source, actor: str = "system") -> Source:
        if source.id in self.sources:
            raise ValueError(f"source {source.id} already exists")
        self.sources[source.id] = source
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="source.registered", entity_type="source", entity_id=source.id,
            before_state={}, after_state={"status": source.status.value, "name": source.name}, occurred_at=utc_now(),
        ))
        self.persist()
        return source

    def set_source_status(self, source_id: str, status: SourceStatus, actor: str = "system") -> Source:
        source = self.get_source(source_id)
        before = {"status": source.status.value}
        source.status = status
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="source.status_changed", entity_type="source", entity_id=source.id,
            before_state=before, after_state={"status": source.status.value}, occurred_at=utc_now(),
        ))
        self.persist()
        return source

    def set_source_policy(self, source_id: str, policy: SourcePolicy, actor: str) -> Source:
        source = self.get_source(source_id)
        if source.policy and source.policy.version == policy.version:
            raise ValueError("a policy version cannot be replaced; submit a new version")
        before = {"policy_version": source.policy.version if source.policy else None}
        source.policy = policy
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="source.policy_submitted", entity_type="source", entity_id=source.id,
            before_state=before, after_state={"policy_version": policy.version, "approved": policy.approved}, occurred_at=utc_now(),
        ))
        self.persist()
        return source

    def approve_source_policy(self, source_id: str, version: str, actor: str) -> Source:
        source = self.get_source(source_id)
        if not source.policy or source.policy.version != version:
            raise ValueError("only the current submitted policy version can be approved")
        if source.policy.approved:
            raise ValueError("policy is already approved")
        before = {"status": source.status.value, "policy_version": version, "approved": False}
        source.policy = replace(source.policy, approved=True)
        source.status = SourceStatus.ACTIVE
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="source.policy_approved", entity_type="source", entity_id=source.id,
            before_state=before, after_state={"status": source.status.value, "policy_version": version, "approved": True}, occurred_at=utc_now(),
        ))
        self.persist()
        return source

    def get_source(self, source_id: str) -> Source:
        try:
            return self.sources[source_id]
        except KeyError as error:
            raise NotFoundError(f"source {source_id} was not found") from error

    def import_csv(self, source_id: str, requested_scope: str, contents: str, parser_version: str = "csv-feed/v1") -> RawCapture:
        rows = parse_csv_feed(contents)
        return self.import_rows(source_id, requested_scope, rows, contents, parser_version)

    def import_rows(
        self,
        source_id: str,
        requested_scope: str,
        rows: list[dict[str, str]],
        raw_contents: str,
        parser_version: str,
    ) -> RawCapture:
        source = self.get_source(source_id)
        assert_source_can_run(source, requested_scope)
        if not rows:
            raise ValueError("source returned no listings")
        body_hash = hashlib.sha256(raw_contents.encode("utf-8")).hexdigest()
        raw_snapshot_pointer = self._raw_store.put(source_id, body_hash, raw_contents.encode("utf-8"))
        capture = RawCapture(
            id=new_id(),
            source_id=source_id,
            request_url=requested_scope,
            fetched_at=utc_now(),
            content_hash=body_hash,
            parser_version=parser_version,
            row_count=len(rows),
            raw_snapshot_pointer=raw_snapshot_pointer,
        )
        self.captures[capture.id] = capture
        for row in rows:
            self._upsert_row(source, capture, row)
        self.persist()
        return capture

    def _upsert_row(self, source: Source, capture: RawCapture, row: dict[str, str]) -> None:
        external_id = row["external_id"].strip()
        canonical_url = row["canonical_url"].strip()
        if not external_id or not canonical_url:
            raise ValueError("external_id and canonical_url are required for every listing")
        parsed = urlparse(canonical_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"listing {external_id} has an invalid canonical HTTPS URL")
        content_hash = hashlib.sha256(repr(sorted(row.items())).encode("utf-8")).hexdigest()
        external_key = (source.id, external_id)
        existing_id = self._external_offer_keys.get(external_key)
        if existing_id and self.offers[existing_id].content_hash == content_hash:
            return
        normalized = normalize_listing(row)
        if not normalized.title:
            raise ValueError(f"listing {external_id} has no title")
        # Only an MPN is a cross-source identity key in this MVP. Missing MPNs
        # remain source-listing-specific rather than being silently merged.
        key = (
            (normalized.manufacturer.lower() if normalized.manufacturer else None, normalized.mpn)
            if normalized.mpn
            else (source.id, f"listing:{external_id}")
        )
        product_id = self._product_keys.get(key)
        if not product_id:
            product = Product(
                id=new_id(),
                manufacturer=normalized.manufacturer,
                mpn=normalized.mpn,
                normalized_name=normalized.title,
                category=normalized.category,
            )
            self.products[product.id] = product
            self._product_keys[key] = product.id
            product_id = product.id
        offer = Offer(
            id=existing_id or new_id(),
            source_id=source.id,
            external_id=external_id,
            canonical_url=canonical_url,
            title=normalized.title,
            product_id=product_id,
            seller_name=row["seller_name"].strip(),
            price_status=normalized.price_status,
            price=normalized.price,
            currency=normalized.currency,
            unit=normalized.unit,
            pack_quantity=normalized.pack_quantity,
            moq=normalized.moq,
            price_tiers=normalized.price_tiers,
            tax_included=normalized.tax_included,
            shipping_included=normalized.shipping_included,
            availability=normalized.availability,
            observed_at=capture.fetched_at,
            raw_capture_id=capture.id,
            content_hash=content_hash,
        )
        self.offers[offer.id] = offer
        self._external_offer_keys[external_key] = offer.id

    def search(
        self,
        query: str,
        quantity: int | None = None,
        category: str | None = None,
        manufacturer: str | None = None,
        price_status: PriceStatus | None = None,
        fresh_only: bool = False,
        max_price_inr: Decimal | None = None,
    ) -> list[dict[str, object]]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        now = utc_now()
        ranked = rank_offers(query, self.products, list(self.offers.values()), self.sources, now, quantity)
        category_key = category.lower().strip() if category else None
        manufacturer_key = manufacturer.lower().strip() if manufacturer else None
        ranked = [
            item for item in ranked
            if (not category_key or (self.products[item.offer.product_id].category or "").lower() == category_key)
            and (not manufacturer_key or (self.products[item.offer.product_id].manufacturer or "").lower() == manufacturer_key)
            and (not price_status or item.offer.price_status is price_status)
            and (not fresh_only or item.freshness.value == "fresh")
            and (max_price_inr is None or item.offer.price_status is not PriceStatus.PUBLIC or item.offer.currency != "INR" or (effective_price(item.offer, quantity) is not None and effective_price(item.offer, quantity) <= max_price_inr))
        ]
        groups = group_by_product(ranked)
        response: list[dict[str, object]] = []
        for product_id, group in groups.items():
            product = self.products[product_id]
            offers = []
            for item in group:
                offer = item.offer
                offers.append({
                    "id": offer.id,
                    "seller_name": offer.seller_name,
                    "source_name": self.sources[offer.source_id].name,
                    "source_url": offer.canonical_url,
                    "price_status": offer.price_status.value,
                    "price": str(effective_price(offer, quantity)) if effective_price(offer, quantity) is not None else None,
                    "currency": offer.currency,
                    "unit": offer.unit,
                    "pack_quantity": offer.pack_quantity,
                    "tax_included": offer.tax_included,
                    "shipping_included": offer.shipping_included,
                    "moq": offer.moq,
                    "availability": offer.availability,
                    "observed_at": offer.observed_at.isoformat(),
                    "freshness": item.freshness.value,
                    "score": round(item.score, 3),
                    "reasons": list(item.reasons),
                })
            response.append({
                "product": {
                    "id": product.id,
                    "manufacturer": product.manufacturer,
                    "mpn": product.mpn,
                    "normalized_name": product.normalized_name,
                    "category": product.category,
                },
                "offers": offers,
            })
        return response

    def source_health(self) -> list[dict[str, object]]:
        """Compute source-level quality signals from stored evidence, not estimates."""
        now = utc_now()
        reports: list[dict[str, object]] = []
        for source in self.sources.values():
            offers = [offer for offer in self.offers.values() if offer.source_id == source.id]
            captures = [capture for capture in self.captures.values() if capture.source_id == source.id]
            freshness = {"fresh": 0, "aging": 0, "stale": 0, "source_unavailable": 0}
            for offer in offers:
                freshness[freshness_for(offer, source, now).value] += 1
            public_offers = [offer for offer in offers if offer.price_status is PriceStatus.PUBLIC]
            complete_public_prices = [offer for offer in public_offers if offer.price is not None and offer.currency and offer.unit]
            commercial_complete = [offer for offer in offers if offer.moq is not None and offer.unit and offer.canonical_url]
            source_events = [event for event in self.outbound_events if event.offer_id in {offer.id for offer in offers}]
            reports.append({
                "source_id": source.id,
                "source_name": source.name,
                "status": source.status.value,
                "policy_version": source.policy.version if source.policy else None,
                "policy_approved": source.policy.approved if source.policy else False,
                "capture_count": len(captures),
                "offer_count": len(offers),
                "freshness": freshness,
                "public_price_completeness": round(len(complete_public_prices) / len(public_offers), 3) if public_offers else None,
                "commercial_field_completeness": round(len(commercial_complete) / len(offers), 3) if offers else None,
                "outbound_events": len(source_events),
                "redirect_failures": sum(1 for event in source_events if event.redirect_status >= 400),
            })
        return sorted(reports, key=lambda report: str(report["source_name"]).lower())

    def search_facets(self) -> dict[str, list[dict[str, object]]]:
        """Return filter values from offers currently eligible for buyer search."""
        now = utc_now()
        eligible = [
            offer for offer in self.offers.values()
            if self.sources[offer.source_id].status is SourceStatus.ACTIVE
            and self.sources[offer.source_id].policy
            and self.sources[offer.source_id].policy.approved
            and freshness_for(offer, self.sources[offer.source_id], now).value != "stale"
        ]

        def counts(values: list[str | None]) -> list[dict[str, object]]:
            frequency: dict[str, int] = {}
            for value in values:
                if value:
                    frequency[value] = frequency.get(value, 0) + 1
            return [{"value": value, "count": count} for value, count in sorted(frequency.items(), key=lambda item: item[0].lower())]

        return {
            "categories": counts([self.products[offer.product_id].category for offer in eligible]),
            "manufacturers": counts([self.products[offer.product_id].manufacturer for offer in eligible]),
            "price_statuses": counts([offer.price_status.value for offer in eligible]),
        }

    def create_match_review(self, offer_id: str, candidate_product_id: str, actor: str) -> MatchReview:
        offer = self.offer_detail(offer_id)
        candidate = self.products.get(candidate_product_id)
        if not candidate:
            raise NotFoundError(f"product {candidate_product_id} was not found")
        if offer.product_id == candidate_product_id:
            raise ValueError("an offer cannot be reviewed against its current product")
        current_product = self.products[offer.product_id]
        title_tokens = set(offer.title.lower().split())
        candidate_tokens = set(candidate.normalized_name.lower().split())
        review = MatchReview(
            id=new_id(), offer_id=offer.id, candidate_product_id=candidate_product_id,
            features={
                "same_category": current_product.category == candidate.category,
                "title_token_overlap": len(title_tokens & candidate_tokens),
                "offer_mpn": current_product.mpn,
                "candidate_mpn": candidate.mpn,
            },
            decision=MatchDecision.NEEDS_REVIEW, reviewer=None, reason=None, created_at=utc_now(),
        )
        self.match_reviews[review.id] = review
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="match.review_created", entity_type="match_review", entity_id=review.id,
            before_state={}, after_state={"offer_id": offer_id, "candidate_product_id": candidate_product_id}, occurred_at=utc_now(),
        ))
        self.persist()
        return review

    def decide_match_review(self, review_id: str, decision: MatchDecision, reason: str, actor: str) -> MatchReview:
        review = self.match_reviews.get(review_id)
        if not review:
            raise NotFoundError(f"match review {review_id} was not found")
        if review.decision is not MatchDecision.NEEDS_REVIEW:
            raise ValueError("a match review has already been decided")
        if decision is MatchDecision.NEEDS_REVIEW:
            raise ValueError("a final review decision must be approved or rejected")
        if not reason.strip():
            raise ValueError("a decision reason is required")
        before = {"decision": review.decision.value}
        review.decision = decision
        review.reviewer = actor
        review.reason = reason.strip()
        review.decided_at = utc_now()
        self.audit_events.append(AuditEvent(
            id=new_id(), actor=actor, action="match.review_decided", entity_type="match_review", entity_id=review.id,
            before_state=before, after_state={"decision": decision.value, "reason": review.reason}, occurred_at=utc_now(),
        ))
        self.persist()
        return review

    def pending_match_reviews(self) -> list[MatchReview]:
        return sorted(
            (review for review in self.match_reviews.values() if review.decision is MatchDecision.NEEDS_REVIEW),
            key=lambda review: review.created_at,
        )

    def product_detail(self, product_id: str) -> dict[str, object]:
        product = self.products.get(product_id)
        if not product:
            raise NotFoundError(f"product {product_id} was not found")
        groups = self.search(product.mpn or product.normalized_name)
        return next((group for group in groups if group["product"]["id"] == product_id), {"product": product, "offers": []})

    def compare(self, offer_ids: list[str], quantity: int | None = None) -> dict[str, object]:
        unique_ids = list(dict.fromkeys(offer_ids))
        if not 2 <= len(unique_ids) <= 5:
            raise ValueError("compare requires between two and five distinct offers")
        offers = [self.offer_detail(offer_id) for offer_id in unique_ids]
        product_ids = {offer.product_id for offer in offers}
        if len(product_ids) != 1:
            raise ValueError("only offers for the same canonical product can be compared in this MVP")
        now = utc_now()
        rows: list[dict[str, object]] = []
        price_eligible_offers = [
            offer for offer in offers
            if offer.price_status.value == "public" and offer.price is not None and offer.unit
            and (quantity is None or offer.moq is None or quantity >= offer.moq)
        ]
        price_bases = {(offer.currency, offer.unit, offer.pack_quantity) for offer in price_eligible_offers}
        best_price = min((effective_price(offer, quantity) for offer in price_eligible_offers), default=None) if len(price_bases) == 1 else None
        known_moqs = [offer.moq for offer in offers if offer.moq is not None]
        lowest_moq = min(known_moqs) if known_moqs else None
        for offer in offers:
            source = self.sources[offer.source_id]
            freshness = freshness_for(offer, source, now)
            quantity_eligible = quantity is None or offer.moq is None or quantity >= offer.moq
            badges: list[dict[str, str]] = []
            if best_price is not None and effective_price(offer, quantity) == best_price and offer.price_status.value == "public" and quantity_eligible:
                badges.append({"kind": "best_price", "label": "Best price at requested quantity"})
            if lowest_moq is not None and offer.moq == lowest_moq:
                badges.append({"kind": "lowest_moq", "label": "Lowest MOQ"})
            if freshness.value == "fresh":
                badges.append({"kind": "freshest", "label": "Within source freshness SLA"})
            if offer.price_status.value == "quote_only":
                badges.append({"kind": "request_quote", "label": "Request quote"})
            rows.append({
                "offer_id": offer.id,
                "seller_name": offer.seller_name,
                "source_name": source.name,
                "source_url": offer.canonical_url,
                "price_status": offer.price_status.value,
                "price": str(effective_price(offer, quantity)) if effective_price(offer, quantity) is not None else None,
                "currency": offer.currency,
                "unit": offer.unit,
                "pack_quantity": offer.pack_quantity,
                "tax_included": offer.tax_included,
                "shipping_included": offer.shipping_included,
                "moq": offer.moq,
                "availability": offer.availability,
                "freshness": freshness.value,
                "observed_at": offer.observed_at.isoformat(),
                "quantity_eligible": quantity_eligible,
                "price_comparable": best_price is not None and offer in price_eligible_offers,
                "badges": badges,
            })
        product = self.products[offers[0].product_id]
        return {
            "product": {"id": product.id, "manufacturer": product.manufacturer, "mpn": product.mpn, "normalized_name": product.normalized_name},
            "quantity": quantity,
            "offers": rows,
            "warnings": ["Prices are comparable only when currency, unit, pack basis, and requested quantity are compatible. Tax and freight remain unknown unless supplied by the source."],
        }

    def offer_detail(self, offer_id: str) -> Offer:
        try:
            return self.offers[offer_id]
        except KeyError as error:
            raise NotFoundError(f"offer {offer_id} was not found") from error

    def outbound(self, offer_id: str, placement: str, session_pseudonym: str | None) -> str:
        offer = self.offer_detail(offer_id)
        source = self.get_source(offer.source_id)
        assert_outbound_url_allowed(source, offer.canonical_url)
        self.outbound_events.append(OutboundEvent(
            id=new_id(),
            offer_id=offer_id,
            occurred_at=utc_now(),
            placement=placement,
            session_pseudonym=session_pseudonym,
            redirect_status=302,
        ))
        self.persist()
        return offer.canonical_url


def build_seeded_catalog(persistence: CatalogPersistence | None = None, raw_store: RawCaptureStore | None = None) -> Catalog:
    catalog = Catalog(persistence=persistence, raw_store=raw_store)
    fixtures = (
        (Source(
            id="cooperative-electronics", name="Cooperative Electronics Feed (fixture)", base_url="https://supplier.example.in",
            owner="catalog-operations@example.invalid", status=SourceStatus.ACTIVE,
            policy=SourcePolicy("2026-09-01", True, ("https://supplier.example.in/feeds/",), ("supplier.example.in",), 10, 24, "https://supplier.example.in/partner-feed-agreement"),
        ), "cooperative_supplier_catalog.csv", "https://supplier.example.in/feeds/catalog.csv"),
        (Source(
            id="partner-components-feed", name="Partner Components Feed (fixture)", base_url="https://partner.example.in",
            owner="partner-operations@example.invalid", status=SourceStatus.ACTIVE,
            policy=SourcePolicy("2026-09-01", True, ("https://partner.example.in/catalogue/",), ("partner.example.in",), 8, 24, "https://partner.example.in/feed-agreement"),
        ), "partner_components_catalog.csv", "https://partner.example.in/catalogue/feed.csv"),
    )
    fixture_dir = Path(__file__).parents[2] / "fixtures"
    for source, filename, scope in fixtures:
        catalog.register_source(source)
        catalog.import_csv(source.id, scope, (fixture_dir / filename).read_text(encoding="utf-8"))
    return catalog


def build_catalog() -> Catalog:
    """Choose PostgreSQL when configured; otherwise run the fixture-backed demo."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return build_seeded_catalog()
    from app.application.postgres import PostgresCatalogPersistence

    persistence = PostgresCatalogPersistence(database_url)
    catalog = persistence.load()
    return catalog if catalog.sources else build_seeded_catalog(persistence)
