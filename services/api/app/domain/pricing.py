from __future__ import annotations

from decimal import Decimal

from .models import Offer


def effective_price(offer: Offer, quantity: int | None) -> Decimal | None:
    """Select only a source-declared quantity tier; never estimate a price."""
    if quantity is None or not offer.price_tiers:
        return offer.price
    for tier in sorted(offer.price_tiers, key=lambda item: item.minimum_quantity, reverse=True):
        if quantity >= tier.minimum_quantity and (tier.maximum_quantity is None or quantity <= tier.maximum_quantity):
            return tier.price
    return offer.price
