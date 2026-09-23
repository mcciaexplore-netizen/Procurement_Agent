from datetime import UTC, datetime

import pytest

from app.connectors.mouser import MouserError, MouserSearchClient, mouser_parts_to_rows
from app.operational import DailyRequestQuota


MOUSER_RESPONSE = {
    "SearchResults": {
        "Parts": [{
            "MouserPartNumber": "595-LM358DR",
            "ManufacturerPartNumber": "LM358DR",
            "Manufacturer": "Texas Instruments",
            "Description": "Operational Amplifier",
            "Category": "Amplifier ICs",
            "ProductDetailUrl": "https://www.mouser.com/ProductDetail/595-LM358DR",
            "PriceBreaks": [{"Quantity": 1, "Price": "$0.50"}, {"Quantity": 10, "Price": "$0.40"}],
            "Min": 1,
            "Mult": 1,
            "Availability": "1,250 In Stock",
        }]
    }
}


def test_mouser_mapping_preserves_provider_facts() -> None:
    rows = mouser_parts_to_rows(MOUSER_RESPONSE)

    assert rows == [{
        "external_id": "595-LM358DR", "canonical_url": "https://www.mouser.com/ProductDetail/595-LM358DR",
        "title": "Operational Amplifier", "seller_name": "Mouser Electronics", "manufacturer": "Texas Instruments",
        "mpn": "LM358DR", "category": "Amplifier ICs", "price": "0.50", "currency": "USD", "unit": "each",
        "price_status": "public", "quantity_breaks": "1-9:0.50;10+:0.40", "moq": "1", "pack_quantity": "1",
        "availability": "1,250 In Stock", "tax_included": "", "shipping_included": "",
    }]


def test_mouser_mapping_rejects_unusable_response() -> None:
    with pytest.raises(MouserError):
        mouser_parts_to_rows({"SearchResults": {"Parts": []}})


def test_mouser_mapping_falls_back_to_mpn_search_link_when_part_number_is_placeholder() -> None:
    response = {
        "SearchResults": {
            "Parts": [{
                "MouserPartNumber": "N/A",
                "ManufacturerPartNumber": "LM358DR",
                "Manufacturer": "Texas Instruments",
                "Description": "Operational Amplifier",
                "Category": "Amplifier ICs",
                "ProductDetailUrl": "",
                "PriceBreaks": [],
                "Min": 1,
                "Mult": 1,
                "Availability": "",
            }]
        }
    }

    rows = mouser_parts_to_rows(response)

    assert rows[0]["canonical_url"] == "https://www.mouser.com/c/?q=LM358DR"


def test_mouser_mapping_rejects_placeholder_part_number_with_no_mpn() -> None:
    response = {
        "SearchResults": {
            "Parts": [{
                "MouserPartNumber": "N/A",
                "ManufacturerPartNumber": "",
                "Manufacturer": "Texas Instruments",
                "Description": "Operational Amplifier",
                "Category": "Amplifier ICs",
                "ProductDetailUrl": "",
                "PriceBreaks": [],
                "Min": 1,
                "Mult": 1,
                "Availability": "",
            }]
        }
    }

    with pytest.raises(MouserError):
        mouser_parts_to_rows(response)


def test_mouser_client_uses_part_number_request() -> None:
    class FakeTransport:
        seen_url = ""
        seen_payload: dict[str, object] = {}

        def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
            self.seen_url, self.seen_payload = url, payload
            return MOUSER_RESPONSE

    transport = FakeTransport()
    response, rows = MouserSearchClient(transport).search_part_number(" LM358DR ")

    assert response == MOUSER_RESPONSE
    assert rows[0]["mpn"] == "LM358DR"
    assert transport.seen_payload == {"SearchByPartRequest": {"mouserPartNumber": "LM358DR", "partSearchOptions": "None"}}


def test_mouser_client_uses_keyword_request() -> None:
    class FakeTransport:
        seen_url = ""
        seen_payload: dict[str, object] = {}

        def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
            self.seen_url, self.seen_payload = url, payload
            return MOUSER_RESPONSE

    transport = FakeTransport()
    response, rows = MouserSearchClient(transport).search_keyword(" arduino uno ")

    assert response == MOUSER_RESPONSE
    assert rows[0]["mpn"] == "LM358DR"
    assert transport.seen_url == "https://api.mouser.com/api/v1/search/keyword"
    assert transport.seen_payload == {
        "SearchByKeywordRequest": {
            "keyword": "arduino uno",
            "records": 10,
            "startingRecord": 0,
            "searchOptions": "",
            "searchWithYourSignUpLanguage": "",
        }
    }


def test_mouser_client_rejects_empty_keyword() -> None:
    with pytest.raises(ValueError):
        MouserSearchClient(transport=None).search_keyword("   ")


def test_daily_quota_resets_at_utc_day_boundary() -> None:
    quota = DailyRequestQuota(limit=1)

    assert quota.consume("mouser", datetime(2026, 9, 6, 23, 59, tzinfo=UTC))
    assert not quota.consume("mouser", datetime(2026, 9, 6, 23, 59, tzinfo=UTC))
    assert quota.consume("mouser", datetime(2026, 9, 7, 0, 0, tzinfo=UTC))
