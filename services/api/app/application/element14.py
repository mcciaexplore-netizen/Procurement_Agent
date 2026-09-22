"""Quota-limited element14 acquisition service."""
from __future__ import annotations
import json
import os
from app.application.catalog import Catalog
from app.connectors.element14 import Element14SearchClient, UrlLibElement14Transport
from app.operational import DailyRequestQuota, SlidingWindowRateLimiter

ELEMENT14_SOURCE_ID = "element14-search-api"
ELEMENT14_SCOPE = "https://api.element14.com/catalog/products"

class Element14AcquisitionService:
    def __init__(self, catalog: Catalog, client: Element14SearchClient, per_minute: int = 5, per_day: int = 100) -> None:
        self.catalog, self.client = catalog, client
        self.per_minute, self.per_day = SlidingWindowRateLimiter(per_minute), DailyRequestQuota(per_day)

    @classmethod
    def from_environment(cls, catalog: Catalog) -> "Element14AcquisitionService":
        api_key = os.getenv("ELEMENT14_API_KEY")
        if not api_key:
            raise RuntimeError("ELEMENT14_API_KEY is not configured")
        per_minute = min(max(int(os.getenv("ELEMENT14_MAX_CALLS_PER_MINUTE", "5")), 1), 5)
        per_day = min(max(int(os.getenv("ELEMENT14_MAX_CALLS_PER_DAY", "100")), 1), 100)
        store_id = os.getenv("ELEMENT14_STORE_ID", "in.element14.com")
        return cls(catalog, Element14SearchClient(UrlLibElement14Transport(api_key), store_id), per_minute, per_day)

    def lookup_part_number(self, part_number: str) -> object:
        if not self.per_minute.allow(ELEMENT14_SOURCE_ID): raise RuntimeError("element14 safety budget reached: retry in one minute")
        if not self.per_day.consume(ELEMENT14_SOURCE_ID): raise RuntimeError("element14 safety budget reached: retry tomorrow")
        response, rows = self.client.search_part_number(part_number)
        return self.catalog.import_rows(ELEMENT14_SOURCE_ID, ELEMENT14_SCOPE, rows, json.dumps(response, sort_keys=True, separators=(",", ":")), parser_version="element14-search-api/v1")

_service: Element14AcquisitionService | None = None
def configured_element14_service(catalog: Catalog) -> Element14AcquisitionService:
    global _service
    if _service is None: _service = Element14AcquisitionService.from_environment(catalog)
    return _service
