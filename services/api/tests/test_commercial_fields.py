import pytest

from app.domain.normalization import normalize_listing, parse_optional_boolean


def test_commercial_inclusions_are_explicit_or_unknown() -> None:
    listing = normalize_listing({
        "title": "Example part", "price": "100", "currency": "INR", "tax_included": "yes", "shipping_included": "unknown",
    })

    assert listing.tax_included is True
    assert listing.shipping_included is None


def test_commercial_inclusions_reject_ambiguous_values() -> None:
    with pytest.raises(ValueError):
        parse_optional_boolean("probably")
