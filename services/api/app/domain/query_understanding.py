"""Conservative query understanding for procurement search.

This is deterministic scaffolding for a later schema-constrained AI parser. It
only extracts values that have an explicit textual signal and keeps the original
query as the retrieval fallback.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation


QUANTITY = re.compile(r"(?:quantity|qty)\s*[:=]?\s*([\d,]+)|\b([\d,]+)\s*(?:units?|pcs?|pieces?)\b", re.IGNORECASE)
BUDGET = re.compile(r"(?:under|below|less than|<)\s*(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
LOCATION = re.compile(r"\b(?:in|near)\s+([A-Za-z][A-Za-z .-]{1,40})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class QueryPlan:
    original_query: str
    retrieval_query: str
    quantity: int | None
    max_price_inr: Decimal | None
    location: str | None
    warnings: tuple[str, ...]

    def response(self) -> dict[str, object]:
        result = asdict(self)
        result["max_price_inr"] = str(self.max_price_inr) if self.max_price_inr is not None else None
        result["warnings"] = list(self.warnings)
        return result


def parse_query(query: str) -> QueryPlan:
    quantity_match = QUANTITY.search(query)
    quantity_text = next((value for value in quantity_match.groups() if value), None) if quantity_match else None
    quantity = int(quantity_text.replace(",", "")) if quantity_text else None
    budget_match = BUDGET.search(query)
    try:
        max_price = Decimal(budget_match.group(1).replace(",", "")) if budget_match else None
    except InvalidOperation:
        max_price = None
    location_match = LOCATION.search(query)
    location = location_match.group(1).strip() if location_match else None
    retrieval = QUANTITY.sub("", BUDGET.sub("", query))
    if location_match:
        retrieval = LOCATION.sub("", retrieval).strip()
    retrieval = re.sub(r"\s+", " ", retrieval).strip(" ,.-") or query
    warnings: list[str] = []
    if max_price is not None:
        warnings.append("Budget applies only to public INR offers with a compatible unit and quantity tier; quote-only and unknown prices remain visible.")
    if location:
        warnings.append("Location is recorded for transparency but is not yet a source-location filter.")
    return QueryPlan(query, retrieval, quantity, max_price, location, tuple(warnings))
