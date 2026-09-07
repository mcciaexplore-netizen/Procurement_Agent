"""Strict contract for a supplier-submitted CSV catalogue feed."""

from __future__ import annotations

import csv
from io import StringIO


REQUIRED_COLUMNS = frozenset({"external_id", "canonical_url", "title", "price", "seller_name"})


class FeedContractError(ValueError):
    pass


def parse_csv_feed(contents: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(StringIO(contents)))
    if not rows:
        raise FeedContractError("feed contains no listings")
    fieldnames = set(rows[0])
    missing = REQUIRED_COLUMNS - fieldnames
    if missing:
        raise FeedContractError(f"feed is missing required columns: {', '.join(sorted(missing))}")
    duplicate_ids: set[str] = set()
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        external_id = (row.get("external_id") or "").strip()
        if not external_id:
            raise FeedContractError(f"row {index} is missing external_id")
        if external_id in seen_ids:
            duplicate_ids.add(external_id)
        seen_ids.add(external_id)
        if not (row.get("canonical_url") or "").startswith("https://"):
            raise FeedContractError(f"row {index} must include an HTTPS canonical_url")
    if duplicate_ids:
        raise FeedContractError(f"feed has duplicate external IDs: {', '.join(sorted(duplicate_ids))}")
    return rows
