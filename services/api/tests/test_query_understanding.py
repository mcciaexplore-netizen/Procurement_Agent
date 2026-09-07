from app.application.catalog import build_seeded_catalog
from app.domain.query_understanding import parse_query


def test_query_plan_extracts_only_explicit_procurement_constraints() -> None:
    plan = parse_query("STM32F407VGT6 quantity 500 under Rs 425 in Mumbai")

    assert plan.retrieval_query == "STM32F407VGT6"
    assert plan.quantity == 500
    assert str(plan.max_price_inr) == "425"
    assert plan.location == "Mumbai"
    assert len(plan.warnings) == 2


def test_budget_filter_does_not_hide_quote_only_or_unknown_offers() -> None:
    catalog = build_seeded_catalog()
    plan = parse_query("STM32F407VGT6 quantity 500 under Rs 425")

    groups = catalog.search(plan.retrieval_query, plan.quantity, max_price_inr=plan.max_price_inr)

    offers = groups[0]["offers"]
    assert {offer["seller_name"] for offer in offers} == {"Cooperative Electronics"}
