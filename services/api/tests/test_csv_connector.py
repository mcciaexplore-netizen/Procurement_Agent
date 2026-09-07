import pytest

from app.connectors.csv_feed import FeedContractError, parse_csv_feed


def test_csv_contract_accepts_the_partner_feed_fixture() -> None:
    contents = "external_id,canonical_url,title,price,seller_name\nA-1,https://supplier.example.in/a,Example,10,Example Seller\n"

    rows = parse_csv_feed(contents)

    assert rows[0]["external_id"] == "A-1"


@pytest.mark.parametrize("contents", [
    "external_id,title,price,seller_name\nA-1,Example,10,Seller\n",
    "external_id,canonical_url,title,price,seller_name\nA-1,http://supplier.example.in/a,Example,10,Seller\n",
    "external_id,canonical_url,title,price,seller_name\nA-1,https://supplier.example.in/a,One,10,Seller\nA-1,https://supplier.example.in/b,Two,20,Seller\n",
])
def test_csv_contract_rejects_invalid_or_duplicate_supplier_rows(contents: str) -> None:
    with pytest.raises(FeedContractError):
        parse_csv_feed(contents)
