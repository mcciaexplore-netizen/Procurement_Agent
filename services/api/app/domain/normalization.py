from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import PriceStatus, PriceTier


MPN_SEPARATORS = re.compile(r"[^A-Z0-9]+")
INTEGER = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    manufacturer: str | None
    mpn: str | None
    title: str
    category: str | None
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


def normalize_mpn(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    compact = MPN_SEPARATORS.sub("", value.upper())
    return compact or None


def parse_positive_integer(value: str | None) -> int | None:
    if not value:
        return None
    match = INTEGER.search(value.replace(",", ""))
    if not match:
        return None
    parsed = int(match.group(0))
    return parsed if parsed > 0 else None


def parse_price(value: str | None, currency: str | None) -> tuple[PriceStatus, Decimal | None, str | None]:
    if not value or not value.strip():
        return PriceStatus.UNKNOWN, None, currency or None
    candidate = value.strip().lower()
    if "quote" in candidate or "rfq" in candidate:
        return PriceStatus.QUOTE_ONLY, None, currency or None
    cleaned = re.sub(r"[^0-9.]", "", candidate.replace(",", ""))
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return PriceStatus.UNKNOWN, None, currency or None
    if amount < 0:
        return PriceStatus.UNKNOWN, None, currency or None
    inferred_currency = currency or ("INR" if "₹" in value or "rs" in candidate else None)
    return PriceStatus.PUBLIC, amount, inferred_currency.upper() if inferred_currency else None


def parse_price_tiers(value: str | None) -> tuple[PriceTier, ...]:
    if not value or not value.strip():
        return ()
    tiers: list[PriceTier] = []
    for raw_tier in value.split(";"):
        try:
            quantity_range, raw_price = raw_tier.split(":", maxsplit=1)
            if quantity_range.strip().endswith("+"):
                minimum, maximum = int(quantity_range.strip()[:-1]), None
            else:
                minimum_text, maximum_text = quantity_range.split("-", maxsplit=1)
                minimum, maximum = int(minimum_text), int(maximum_text)
            price = Decimal(re.sub(r"[^0-9.]", "", raw_price.replace(",", "")))
        except (ValueError, InvalidOperation):
            raise ValueError(f"invalid price tier: {raw_tier}") from None
        if minimum < 1 or (maximum is not None and maximum < minimum) or price < 0:
            raise ValueError(f"invalid price tier: {raw_tier}")
        tiers.append(PriceTier(minimum, maximum, price))
    ordered = sorted(tiers, key=lambda tier: tier.minimum_quantity)
    if any(current.minimum_quantity <= previous.maximum_quantity for previous, current in zip(ordered, ordered[1:]) if previous.maximum_quantity is not None):
        raise ValueError("price tiers must not overlap")
    return tuple(ordered)


def parse_optional_boolean(value: str | None) -> bool | None:
    if not value or not value.strip() or value.strip().lower() in {"unknown", "n/a"}:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "included"}:
        return True
    if normalized in {"false", "no", "excluded"}:
        return False
    raise ValueError(f"invalid boolean field: {value}")


def normalize_listing(row: dict[str, str]) -> NormalizedListing:
    price_status, price, currency = parse_price(row.get("price"), row.get("currency"))
    return NormalizedListing(
        manufacturer=(row.get("manufacturer") or "").strip() or None,
        mpn=normalize_mpn(row.get("mpn")),
        title=(row.get("title") or "").strip(),
        category=(row.get("category") or "").strip() or None,
        price_status=price_status,
        price=price,
        currency=currency,
        unit=(row.get("unit") or "").strip().lower() or None,
        pack_quantity=parse_positive_integer(row.get("pack_quantity")),
        moq=parse_positive_integer(row.get("moq")),
        price_tiers=parse_price_tiers(row.get("quantity_breaks")),
        tax_included=parse_optional_boolean(row.get("tax_included")),
        shipping_included=parse_optional_boolean(row.get("shipping_included")),
        availability=(row.get("availability") or "").strip() or None,
    )
