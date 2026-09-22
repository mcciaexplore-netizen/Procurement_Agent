"""Read-only element14/Farnell Product Search API adapter."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, urlparse
from urllib.request import urlopen

ELEMENT14_ENDPOINT = "https://api.element14.com/catalog/products"

class Element14Error(RuntimeError):
    """Safe provider error that never includes the API key."""

class JsonTransport(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> dict[str, object]: ...

@dataclass(frozen=True, slots=True)
class UrlLibElement14Transport:
    api_key: str
    timeout_seconds: float = 12.0

    def get_json(self, url: str, params: dict[str, str]) -> dict[str, object]:
        query = dict(params)
        query["callinfo.apiKey"] = self.api_key
        request_url = f"{url}?{urlencode(query)}"
        try:
            with urlopen(request_url, timeout=self.timeout_seconds) as response:  # nosec B310: fixed approved HTTPS host
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise Element14Error(f"element14 API returned HTTP {error.code}") from error
        except (URLError, TimeoutError):
            raise Element14Error("element14 API is unavailable")
        except json.JSONDecodeError as error:
            raise Element14Error("element14 API returned an invalid response") from error

def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""

def _number(value: object) -> str:
    try:
        return str(Decimal(str(value)).normalize()) if value not in (None, "") else ""
    except (InvalidOperation, ValueError):
        return ""

def element14_products_to_rows(response: dict[str, object], store_id: str) -> list[dict[str, str]]:
    result = response.get("keywordSearchReturn")
    products = result.get("products") if isinstance(result, dict) else None
    if not isinstance(products, list):
        raise Element14Error("element14 response does not contain product results")
    rows: list[dict[str, str]] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        sku, title = _text(item.get("sku")), _text(item.get("displayName"))
        if not sku or not title:
            continue
        prices = item.get("prices")
        first = prices[0] if isinstance(prices, list) and prices and isinstance(prices[0], dict) else {}
        price = _number(first.get("cost"))
        mpn = _text(item.get("translatedManufacturerPartNumber"))
        rows.append({
            "external_id": sku, "canonical_url": f"https://in.element14.com/{quote(sku, safe='')}",
            "title": title, "seller_name": "element14", "manufacturer": _text(item.get("brandName")),
            "mpn": mpn, "category": "Electronic Components", "price": price, "currency": "INR" if price else "",
            "unit": _text(item.get("unitOfMeasure")).lower() or "each", "price_status": "public" if price else "unknown",
            "quantity_breaks": f"1+:{price}" if price else "", "moq": str(item.get("translatedMinimumOrderQuality") or ""),
            "pack_quantity": str(item.get("packSize") or ""), "availability": _text(item.get("productStatus")),
            "tax_included": "", "shipping_included": "",
        })
    if not rows:
        raise Element14Error("element14 returned no usable product results")
    return rows

@dataclass(slots=True)
class Element14SearchClient:
    transport: JsonTransport
    store_id: str = "in.element14.com"

    def search_part_number(self, part_number: str) -> tuple[dict[str, object], list[dict[str, str]]]:
        normalized = part_number.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("part_number must contain between 1 and 128 characters")
        params = {"term": f"manuPartNum:{normalized}", "storeInfo.id": self.store_id, "resultsSettings.offset": "0", "resultsSettings.numberOfResults": "20", "resultsSettings.responseGroup": "medium", "callInfo.responseDataFormat": "JSON"}
        response = self.transport.get_json(ELEMENT14_ENDPOINT, params)
        return response, element14_products_to_rows(response, self.store_id)
