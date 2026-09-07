from pathlib import Path
from datetime import timedelta

import pytest

from app.application.catalog import build_seeded_catalog
from app.application.jobs import stale_offer_sweep
from app.application.raw_store import FilesystemRawCaptureStore, S3RawCaptureStore, build_raw_capture_store
from app.domain.models import utc_now
from app.domain.models import MatchDecision, PriceStatus, Source, SourcePolicy, SourceStatus
from app.domain.policy import PolicyViolation


def test_exact_mpn_groups_offers_and_keeps_provenance() -> None:
    catalog = build_seeded_catalog()

    groups = catalog.search("STM32F407VGT6", quantity=500)

    assert len(groups) == 1
    assert groups[0]["product"]["mpn"] == "STM32F407VGT6"
    assert len(groups[0]["offers"]) == 3
    assert {offer["source_name"] for offer in groups[0]["offers"]} == {
        "Cooperative Electronics Feed (fixture)", "Partner Components Feed (fixture)",
    }
    assert all(offer["source_url"].startswith("https://") for offer in groups[0]["offers"])
    assert all(offer["freshness"] == "fresh" for offer in groups[0]["offers"])


def test_quote_only_listing_is_searchable_without_a_fake_price() -> None:
    catalog = build_seeded_catalog()

    groups = catalog.search("TMP36")
    offer = groups[0]["offers"][0]

    assert offer["price_status"] == "quote_only"
    assert offer["price"] is None


def test_paused_source_disappears_from_search_and_cannot_import() -> None:
    catalog = build_seeded_catalog()
    catalog.set_source_status("cooperative-electronics", SourceStatus.PAUSED, actor="test-admin")

    remaining = catalog.search("STM32F407VGT6")
    assert len(remaining[0]["offers"]) == 1
    assert remaining[0]["offers"][0]["source_name"] == "Partner Components Feed (fixture)"
    fixture = Path(__file__).parents[1] / "fixtures" / "cooperative_supplier_catalog.csv"
    with pytest.raises(PolicyViolation):
        catalog.import_csv("cooperative-electronics", "https://supplier.example.in/feeds/catalog.csv", fixture.read_text())
    assert catalog.audit_events[-1].actor == "test-admin"
    assert catalog.audit_events[-1].action == "source.status_changed"


def test_outbound_rejects_non_allowlisted_listing() -> None:
    catalog = build_seeded_catalog()
    offer = next(iter(catalog.offers.values()))
    offer.canonical_url = "https://untrusted.example/product"

    with pytest.raises(PolicyViolation):
        catalog.outbound(offer.id, "result", None)


def test_feed_import_is_idempotent_for_identical_rows() -> None:
    catalog = build_seeded_catalog()
    fixture = Path(__file__).parents[1] / "fixtures" / "cooperative_supplier_catalog.csv"
    before = len(catalog.offers)

    catalog.import_csv("cooperative-electronics", "https://supplier.example.in/feeds/catalog.csv", fixture.read_text())

    assert len(catalog.offers) == before


def test_raw_capture_is_written_immutably_by_content_hash(tmp_path: Path) -> None:
    store = FilesystemRawCaptureStore(tmp_path)
    catalog = build_seeded_catalog(raw_store=store)
    capture = next(iter(catalog.captures.values()))

    assert capture.raw_snapshot_pointer is not None
    stored_feed = tmp_path / capture.raw_snapshot_pointer
    assert stored_feed.exists()
    assert "STM32F407VGT6" in stored_feed.read_text()


def test_freshness_sweep_records_an_auditable_checkpoint() -> None:
    catalog = build_seeded_catalog()
    offer = next(iter(catalog.offers.values()))
    offer.observed_at = utc_now() - timedelta(hours=72)

    report = stale_offer_sweep(catalog)

    assert report["stale"] == 1
    assert catalog.audit_events[-1].action == "offers.freshness_swept"


def test_compare_labels_price_moq_and_freshness_without_estimates() -> None:
    catalog = build_seeded_catalog()
    offers = catalog.search("STM32F407VGT6", quantity=500)[0]["offers"]

    comparison = catalog.compare([offers[0]["id"], offers[1]["id"]], quantity=500)

    assert comparison["quantity"] == 500
    assert any(badge["kind"] == "best_price" for badge in comparison["offers"][0]["badges"])
    assert "Tax and freight remain unknown" in comparison["warnings"][0]


def test_source_onboarding_requires_policy_approval_before_a_run() -> None:
    catalog = build_seeded_catalog()
    source = Source("new-approved-feed", "New approved feed", "https://new.example.in", "owner@example.in", SourceStatus.DRAFT)
    catalog.register_source(source, actor="source-owner")
    policy = SourcePolicy(
        version="v1", approved=False, allowed_scopes=("https://new.example.in/feed/",),
        allowed_domains=("new.example.in",), rate_budget_per_minute=5, freshness_sla_hours=24,
        evidence_url="https://new.example.in/partner-agreement",
    )
    catalog.set_source_policy(source.id, policy, actor="source-owner")
    fixture = Path(__file__).parents[1] / "fixtures" / "cooperative_supplier_catalog.csv"

    with pytest.raises(PolicyViolation):
        catalog.import_csv(source.id, "https://new.example.in/feed/catalog.csv", fixture.read_text())

    catalog.approve_source_policy(source.id, "v1", actor="approver")
    catalog.import_csv(source.id, "https://new.example.in/feed/catalog.csv", fixture.read_text())

    assert source.status is SourceStatus.ACTIVE
    assert [event.action for event in catalog.audit_events[-3:]] == ["source.registered", "source.policy_submitted", "source.policy_approved"]


def test_search_filters_apply_without_hiding_offer_provenance() -> None:
    catalog = build_seeded_catalog()

    groups = catalog.search("STM32F407VGT6", category="electronic components", manufacturer="stmicroelectronics", price_status=PriceStatus.PUBLIC, fresh_only=True)

    assert len(groups) == 1
    assert all(offer["price_status"] == "public" and offer["source_url"] for offer in groups[0]["offers"])


def test_source_health_reports_completeness_and_freshness_from_evidence() -> None:
    catalog = build_seeded_catalog()

    report = catalog.source_health()[0]

    assert report["offer_count"] == 4
    assert report["freshness"]["fresh"] == 4
    assert report["public_price_completeness"] == 1.0
    assert report["commercial_field_completeness"] == 1.0


def test_match_review_requires_human_final_decision_and_a_reason() -> None:
    catalog = build_seeded_catalog()
    offer = next(offer for offer in catalog.offers.values() if offer.title.startswith("STM32"))
    candidate = next(product for product in catalog.products.values() if product.id != offer.product_id)

    review = catalog.create_match_review(offer.id, candidate.id, actor="operator")

    assert review.decision is MatchDecision.NEEDS_REVIEW
    assert catalog.pending_match_reviews() == [review]
    decided = catalog.decide_match_review(review.id, MatchDecision.REJECTED, "MPN and product family differ", actor="reviewer")
    assert decided.reviewer == "reviewer"
    assert decided.decision is MatchDecision.REJECTED
    assert catalog.pending_match_reviews() == []
    with pytest.raises(ValueError):
        catalog.decide_match_review(review.id, MatchDecision.APPROVED, "Second decision", actor="reviewer")


def test_raw_store_factory_defaults_to_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAW_CAPTURE_BACKEND", raising=False)

    assert isinstance(build_raw_capture_store(), FilesystemRawCaptureStore)


def test_s3_store_uses_immutable_hash_key_without_overwriting() -> None:
    class MissingObject(Exception):
        response = {"Error": {"Code": "404"}}

    class Client:
        def __init__(self) -> None:
            self.buckets: set[str] = set()
            self.objects: dict[tuple[str, str], bytes] = {}

        def head_bucket(self, Bucket: str) -> None:
            if Bucket not in self.buckets:
                raise MissingObject()

        def create_bucket(self, Bucket: str, **_kwargs: object) -> None:
            self.buckets.add(Bucket)

        def head_object(self, Bucket: str, Key: str) -> None:
            if (Bucket, Key) not in self.objects:
                raise MissingObject()

        def put_object(self, Bucket: str, Key: str, Body: bytes, **_kwargs: object) -> None:
            self.objects[(Bucket, Key)] = Body

    client = Client()
    store = S3RawCaptureStore("raw", "http://minio", "key", "secret")
    store._client = lambda: client  # type: ignore[method-assign]
    digest = "a" * 64

    key = store.put("supplier", digest, b"catalogue")
    assert key == f"raw/supplier/aa/{digest}.csv"
    assert client.objects[("raw", key)] == b"catalogue"
    assert store.put("supplier", digest, b"catalogue") == key


def test_search_facets_only_include_current_approved_source_offers() -> None:
    catalog = build_seeded_catalog()
    catalog.set_source_status("partner-components-feed", SourceStatus.PAUSED, actor="operator")

    facets = catalog.search_facets()

    assert {item["value"] for item in facets["categories"]} == {"Electronic Components", "Industrial Materials", "Industrial Sensors"}
    assert next(item for item in facets["manufacturers"] if item["value"] == "STMicroelectronics")["count"] == 2


def test_quantity_price_tier_is_used_for_search_and_comparison() -> None:
    catalog = build_seeded_catalog()

    groups = catalog.search("STM32F407VGT6", quantity=250)
    cooperative_offer = next(offer for offer in groups[0]["offers"] if offer["seller_name"] == "Cooperative Electronics" and offer["moq"] == 100)
    partner_offer = next(offer for offer in groups[0]["offers"] if offer["seller_name"] == "Partner Components")

    assert cooperative_offer["price"] == "450"
    assert partner_offer["price"] == "430"
    comparison = catalog.compare([cooperative_offer["id"], partner_offer["id"]], quantity=250)
    assert comparison["offers"][1]["price"] == "430"
