"""Mouser-specific acquisition service with deliberately conservative quotas."""

from __future__ import annotations

import json
import os

from app.application.catalog import Catalog
from app.connectors.mouser import MouserSearchClient, UrlLibJsonTransport
from app.operational import DailyRequestQuota, SlidingWindowRateLimiter


MOUSER_SOURCE_ID = "mouser-search-api"
MOUSER_SCOPE = "https://api.mouser.com/api/v1/search/partnumber"


class MouserAcquisitionService:
    def __init__(self, catalog: Catalog, client: MouserSearchClient, per_minute: int = 5, per_day: int = 100) -> None:
        self.catalog = catalog
        self.client = client
        self.per_minute = SlidingWindowRateLimiter(per_minute)
        self.per_day = DailyRequestQuota(per_day)

    @classmethod
    def from_environment(cls, catalog: Catalog) -> "MouserAcquisitionService":
        api_key = os.getenv("MOUSER_API_KEY")
        if not api_key:
            raise RuntimeError("MOUSER_API_KEY is not configured")
        # These maximums are intentionally well below Mouser's documented caps.
        per_minute = min(max(int(os.getenv("MOUSER_MAX_CALLS_PER_MINUTE", "5")), 1), 5)
        per_day = min(max(int(os.getenv("MOUSER_MAX_CALLS_PER_DAY", "100")), 1), 100)
        client = MouserSearchClient(UrlLibJsonTransport(api_key=api_key))
        return cls(catalog, client, per_minute=per_minute, per_day=per_day)

    def lookup_part_number(self, part_number: str) -> object:
        if not self.per_minute.allow(MOUSER_SOURCE_ID):
            raise RuntimeError("Mouser safety budget reached: retry in one minute")
        if not self.per_day.consume(MOUSER_SOURCE_ID):
            raise RuntimeError("Mouser safety budget reached: retry tomorrow")
        response, rows = self.client.search_part_number(part_number)
        # Retain raw response for traceability; it never contains the request key.
        return self.catalog.import_rows(
            MOUSER_SOURCE_ID,
            MOUSER_SCOPE,
            rows,
            json.dumps(response, sort_keys=True, separators=(",", ":")),
            parser_version="mouser-search-api/v1",
        )


_service: MouserAcquisitionService | None = None


def configured_mouser_service(catalog: Catalog) -> MouserAcquisitionService:
    """Keep the safety counters alive for the API process lifetime."""
    global _service
    if _service is None:
        _service = MouserAcquisitionService.from_environment(catalog)
    return _service
