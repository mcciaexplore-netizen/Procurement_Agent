"""Read-only Mouser Search API adapter.

This module deliberately exposes product lookup only.  Cart, ordering, and
account endpoints are out of scope for the procurement discovery product.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


MOUSER_PART_NUMBER_ENDPOINT = "https://api.mouser.com/api/v1/search/partnumber"


class MouserError(RuntimeError):
    """A safe, non-secret-bearing error returned by the provider."""


class HttpTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class UrlLibJsonTransport:
    api_key: str
    timeout_seconds: float = 12.0

    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{url}?apiKey={quote(self.api_key, safe='')}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310: fixed approved HTTPS host
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # Deliberately do not include the request URL, which contains the API key.
            raise MouserError(f"Mouser API returned HTTP {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise MouserError("Mouser API is unavailable") from error
        except json.JSONDecodeError as error:
            raise MouserError("Mouser API returned an invalid response") from error


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        return str(int(Decimal(str(value))))
    except (InvalidOperation, ValueError):
        return ""


def _price(value: object) -> str:
    if value is None:
        return ""
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return str(Decimal(cleaned))
    except InvalidOperation:
        return ""


def _canonical_url(part: dict[str, Any]) -> str:
    supplied = _text(part.get("ProductDetailUrl"))
    if supplied:
        parsed = urlparse(supplied)
        if parsed.scheme == "https" and parsed.hostname and parsed.hostname.endswith("mouser.com"):
            return supplied
    mouser_number = _text(part.get("MouserPartNumber"))
    if not mouser_number:
        raise MouserError("Mouser response is missing a part number")
    return f"https://www.mouser.com/ProductDetail/{quote(mouser_number, safe='')}"


def mouser_parts_to_rows(response: dict[str, object]) -> list[dict[str, str]]:
    """Map the documented Search API response into the internal listing contract."""
    results = response.get("SearchResults")
    parts = results.get("Parts") if isinstance(results, dict) else None
    if not isinstance(parts, list):
        raise MouserError("Mouser response does not contain product results")

    rows: list[dict[str, str]] = []
    for item in parts:
        if not isinstance(item, dict):
            continue
        mouser_number = _text(item.get("MouserPartNumber"))
        description = _text(item.get("Description"))
        if not mouser_number or not description:
            continue
        price_breaks = item.get("PriceBreaks")
        first_break = price_breaks[0] if isinstance(price_breaks, list) and price_breaks and isinstance(price_breaks[0], dict) else {}
        price_tiers = [
            (int(_integer(price_break.get("Quantity"))), _price(price_break.get("Price")))
            for price_break in price_breaks or [] if isinstance(price_break, dict) and _integer(price_break.get("Quantity")) and _price(price_break.get("Price"))
        ]
        quantity_breaks = ";".join(
            f"{minimum}-{price_tiers[index + 1][0] - 1}:{price}" if index + 1 < len(price_tiers) else f"{minimum}+:{price}"
            for index, (minimum, price) in enumerate(price_tiers)
        )
        price = _price(first_break.get("Price"))
        rows.append({
            "external_id": mouser_number,
            "canonical_url": _canonical_url(item),
            "title": description,
            "seller_name": "Mouser Electronics",
            "manufacturer": _text(item.get("Manufacturer")) or "",
            "mpn": _text(item.get("ManufacturerPartNumber")) or "",
            "category": _text(item.get("Category")) or "",
            "price": price,
            "currency": "USD" if price else "",
            "unit": "each" if price else "",
            "price_status": "public" if price else "unknown",
            "quantity_breaks": quantity_breaks,
            "moq": _integer(item.get("Min")),
            "pack_quantity": _integer(item.get("Mult")),
            "availability": _text(item.get("Availability")) or "",
            "tax_included": "",
            "shipping_included": "",
        })
    if not rows:
        raise MouserError("Mouser returned no usable product results")
    return rows


@dataclass(slots=True)
class MouserSearchClient:
    transport: HttpTransport

    def search_part_number(self, part_number: str) -> tuple[dict[str, object], list[dict[str, str]]]:
        normalized = part_number.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("part_number must contain between 1 and 128 characters")
        payload: dict[str, object] = {
            "SearchByPartRequest": {"mouserPartNumber": normalized, "partSearchOptions": "None"}
        }
        response = self.transport.post_json(MOUSER_PART_NUMBER_ENDPOINT, payload)
        return response, mouser_parts_to_rows(response)
