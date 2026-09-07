"""PostgreSQL persistence adapter for the catalog aggregate.

The adapter is intentionally synchronous for the MVP. The API can use it behind
one process today and move calls to an async pool without changing the domain
contract. psycopg is imported lazily so pure domain tests stay dependency-free.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid5

from app.application.catalog import Catalog
from app.domain.models import MatchDecision, MatchReview, Offer, PriceStatus, PriceTier, Product, RawCapture, Source, SourcePolicy, SourceStatus


SELLER_NAMESPACE = UUID("d4e0801c-6a32-4b30-a2e8-a119a7d47502")
LISTING_NAMESPACE = UUID("ea65d32a-886b-4e50-9d4b-8fd727830a50")


def listing_id_for(offer: Offer) -> str:
    return str(uuid5(LISTING_NAMESPACE, f"{offer.source_id}:{offer.external_id}"))


class PostgresCatalogPersistence:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover - depends on deployment extras
            raise RuntimeError("PostgreSQL mode requires psycopg; install services/api/requirements.txt") from error
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def sync(self, catalog: Catalog) -> None:
        """Persist the current aggregate atomically after every write command."""
        from psycopg.types.json import Jsonb

        with self._connect() as connection, connection.cursor() as cursor:
            for source in catalog.sources.values():
                cursor.execute(
                    """INSERT INTO sources (id, name, base_url, tier, status, owner)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, base_url = EXCLUDED.base_url,
                    status = EXCLUDED.status, owner = EXCLUDED.owner""",
                    (source.id, source.name, source.base_url, "partner_feed", source.status.value, source.owner),
                )
                if source.policy:
                    cursor.execute(
                        """INSERT INTO source_policies
                        (source_id, version, approved, allowed_scopes, allowed_domains, rate_budget_per_minute,
                         freshness_sla_hours, evidence_url, reviewed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_id, version) DO UPDATE SET approved = EXCLUDED.approved,
                        reviewed_at = EXCLUDED.reviewed_at""",
                        (source.id, source.policy.version, source.policy.approved, Jsonb(list(source.policy.allowed_scopes)),
                         Jsonb(list(source.policy.allowed_domains)), source.policy.rate_budget_per_minute,
                         source.policy.freshness_sla_hours, source.policy.evidence_url, source.policy.reviewed_at),
                    )
            for capture in catalog.captures.values():
                cursor.execute(
                    """INSERT INTO raw_captures (id, source_id, request_url, fetched_at, content_hash, object_key, parser_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                    (capture.id, capture.source_id, capture.request_url, capture.fetched_at, capture.content_hash,
                     capture.raw_snapshot_pointer, capture.parser_version),
                )
            for product in catalog.products.values():
                cursor.execute(
                    """INSERT INTO products (id, manufacturer, mpn, normalized_name, category_id)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                    (product.id, product.manufacturer, product.mpn, product.normalized_name, product.category),
                )
            for offer in catalog.offers.values():
                listing_id = listing_id_for(offer)
                seller_id = str(uuid5(SELLER_NAMESPACE, offer.seller_name.lower()))
                cursor.execute(
                    """INSERT INTO sellers (id, display_name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING""",
                    (seller_id, offer.seller_name),
                )
                cursor.execute(
                    """INSERT INTO source_listings (id, source_id, external_id, canonical_url, title, raw_fields, observed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, external_id) DO UPDATE SET canonical_url = EXCLUDED.canonical_url,
                    title = EXCLUDED.title, raw_fields = EXCLUDED.raw_fields, observed_at = EXCLUDED.observed_at""",
                    (listing_id, offer.source_id, offer.external_id, offer.canonical_url, offer.title,
                     Jsonb({"content_hash": offer.content_hash, "raw_capture_id": offer.raw_capture_id}), offer.observed_at),
                )
                cursor.execute(
                    """INSERT INTO offers (id, source_listing_id, product_id, seller_id, price, currency, unit,
                    pack_quantity, moq, quantity_breaks, price_status, tax_included, shipping_included, availability, observed_at, raw_capture_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_listing_id) DO UPDATE SET product_id = EXCLUDED.product_id,
                    seller_id = EXCLUDED.seller_id, price = EXCLUDED.price, currency = EXCLUDED.currency,
                    unit = EXCLUDED.unit, pack_quantity = EXCLUDED.pack_quantity, moq = EXCLUDED.moq, quantity_breaks = EXCLUDED.quantity_breaks,
                    price_status = EXCLUDED.price_status, tax_included = EXCLUDED.tax_included, shipping_included = EXCLUDED.shipping_included, availability = EXCLUDED.availability,
                    observed_at = EXCLUDED.observed_at, raw_capture_id = EXCLUDED.raw_capture_id""",
                    (offer.id, listing_id, offer.product_id, seller_id, offer.price, offer.currency, offer.unit,
                     offer.pack_quantity, offer.moq, Jsonb([{"minimum_quantity": tier.minimum_quantity, "maximum_quantity": tier.maximum_quantity, "price": str(tier.price)} for tier in offer.price_tiers]), offer.price_status.value, offer.tax_included, offer.shipping_included, offer.availability, offer.observed_at,
                     offer.raw_capture_id),
                )
            for event in catalog.outbound_events:
                cursor.execute(
                    """INSERT INTO outbound_events (id, offer_id, session_pseudonym, placement, redirect_status, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                    (event.id, event.offer_id, event.session_pseudonym, event.placement, event.redirect_status, event.occurred_at),
                )
            for event in catalog.audit_events:
                cursor.execute(
                    """INSERT INTO audit_events (id, actor, action, entity_type, entity_id, before_state, after_state, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                    (event.id, event.actor, event.action, event.entity_type, event.entity_id,
                     Jsonb(event.before_state), Jsonb(event.after_state), event.occurred_at),
                )
            for review in catalog.match_reviews.values():
                offer = catalog.offer_detail(review.offer_id)
                cursor.execute(
                    """INSERT INTO match_reviews (id, source_listing_id, candidate_product_id, decision, features, reason, reviewer, model_version, created_at, decided_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET decision = EXCLUDED.decision, reason = EXCLUDED.reason,
                    reviewer = EXCLUDED.reviewer, decided_at = EXCLUDED.decided_at""",
                    (review.id, listing_id_for(offer), review.candidate_product_id, review.decision.value, Jsonb(review.features),
                     review.reason, review.reviewer, "rules/v1", review.created_at, review.decided_at),
                )

    def load(self) -> Catalog:
        """Hydrate the in-memory read model from PostgreSQL after a restart."""
        catalog = Catalog(persistence=self)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT s.*, p.version, p.approved, p.allowed_scopes, p.allowed_domains,
                p.rate_budget_per_minute, p.freshness_sla_hours, p.evidence_url, p.reviewed_at
                FROM sources s LEFT JOIN LATERAL (
                  SELECT * FROM source_policies WHERE source_id = s.id ORDER BY reviewed_at DESC LIMIT 1
                ) p ON true"""
            )
            for row in cursor.fetchall():
                policy = None
                if row["version"]:
                    policy = SourcePolicy(row["version"], row["approved"], tuple(row["allowed_scopes"]),
                                          tuple(row["allowed_domains"]), row["rate_budget_per_minute"],
                                          row["freshness_sla_hours"], row["evidence_url"], row["reviewed_at"])
                catalog.sources[row["id"]] = Source(row["id"], row["name"], row["base_url"], row["owner"], SourceStatus(row["status"]), policy)
            cursor.execute("SELECT id, source_id, request_url, fetched_at, content_hash, object_key, parser_version FROM raw_captures")
            for row in cursor.fetchall():
                catalog.captures[str(row["id"])] = RawCapture(
                    str(row["id"]), row["source_id"], row["request_url"], row["fetched_at"], row["content_hash"],
                    row["parser_version"], 0, row["object_key"],
                )
            cursor.execute("SELECT id, manufacturer, mpn, normalized_name, category_id FROM products")
            for row in cursor.fetchall():
                product = Product(str(row["id"]), row["manufacturer"], row["mpn"], row["normalized_name"], row["category_id"])
                catalog.products[product.id] = product
                if product.mpn:
                    catalog._product_keys[((product.manufacturer or "").lower() or None, product.mpn)] = product.id
            cursor.execute(
                """SELECT o.*, sl.source_id, sl.external_id, sl.canonical_url, sl.title, sl.raw_fields, se.display_name
                FROM offers o JOIN source_listings sl ON sl.id = o.source_listing_id
                JOIN sellers se ON se.id = o.seller_id"""
            )
            for row in cursor.fetchall():
                raw_fields = row["raw_fields"] or {}
                offer = Offer(str(row["id"]), row["source_id"], row["external_id"], row["canonical_url"], row["title"],
                              str(row["product_id"]), row["display_name"], PriceStatus(row["price_status"]), row["price"], row["currency"],
                              row["unit"], row["pack_quantity"], row["moq"], tuple(PriceTier(item["minimum_quantity"], item.get("maximum_quantity"), Decimal(str(item["price"]))) for item in (row["quantity_breaks"] or [])), row["tax_included"], row["shipping_included"], row["availability"], row["observed_at"],
                              str(row["raw_capture_id"]), raw_fields.get("content_hash", ""))
                catalog.offers[offer.id] = offer
                catalog._external_offer_keys[(offer.source_id, offer.external_id)] = offer.id
            cursor.execute(
                """SELECT r.*, o.id AS offer_id FROM match_reviews r
                JOIN offers o ON o.source_listing_id = r.source_listing_id"""
            )
            for row in cursor.fetchall():
                review = MatchReview(
                    id=str(row["id"]), offer_id=str(row["offer_id"]), candidate_product_id=str(row["candidate_product_id"]),
                    features=row["features"] or {}, decision=MatchDecision(row["decision"]), reviewer=row["reviewer"],
                    reason=row["reason"], created_at=row["created_at"], decided_at=row["decided_at"],
                )
                catalog.match_reviews[review.id] = review
        return catalog
