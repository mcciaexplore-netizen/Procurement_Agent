from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class PriceStatus(StrEnum):
    PUBLIC = "public"
    QUOTE_ONLY = "quote_only"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    SOURCE_UNAVAILABLE = "source_unavailable"


class MatchDecision(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True)
class SourcePolicy:
    version: str
    approved: bool
    allowed_scopes: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    rate_budget_per_minute: int
    freshness_sla_hours: int
    evidence_url: str
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Source:
    id: str
    name: str
    base_url: str
    owner: str
    status: SourceStatus
    policy: SourcePolicy | None = None


@dataclass(slots=True)
class RawCapture:
    id: str
    source_id: str
    request_url: str
    fetched_at: datetime
    content_hash: str
    parser_version: str
    row_count: int
    raw_snapshot_pointer: str | None = None


@dataclass(slots=True)
class Product:
    id: str
    manufacturer: str | None
    mpn: str | None
    normalized_name: str
    category: str | None


@dataclass(frozen=True, slots=True)
class PriceTier:
    minimum_quantity: int
    maximum_quantity: int | None
    price: Decimal


@dataclass(slots=True)
class Offer:
    id: str
    source_id: str
    external_id: str
    canonical_url: str
    title: str
    product_id: str
    seller_name: str
    price_status: PriceStatus
    price: Decimal | None
    currency: str | None
    unit: str | None
    pack_quantity: int | None
    moq: int | None
    price_tiers: tuple[PriceTier, ...]
    tax_included: bool | None
    shipping_included: bool | None
    availability: str | None
    observed_at: datetime
    raw_capture_id: str
    content_hash: str


@dataclass(slots=True)
class OutboundEvent:
    id: str
    offer_id: str
    occurred_at: datetime
    placement: str
    session_pseudonym: str | None
    redirect_status: int


@dataclass(slots=True)
class AuditEvent:
    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    before_state: dict[str, object]
    after_state: dict[str, object]
    occurred_at: datetime


@dataclass(slots=True)
class MatchReview:
    id: str
    offer_id: str
    candidate_product_id: str
    features: dict[str, object]
    decision: MatchDecision
    reviewer: str | None
    reason: str | None
    created_at: datetime
    decided_at: datetime | None = None


def new_id() -> str:
    return str(uuid4())


def serialize(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value
