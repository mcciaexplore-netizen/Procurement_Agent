from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os
from dataclasses import asdict
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.application.catalog import Catalog, NotFoundError, build_catalog
from app.application.mouser import MOUSER_SOURCE_ID, MOUSER_SCOPE, configured_mouser_service
from app.connectors.mouser import MouserError
from app.domain.models import MatchDecision, PriceStatus, Source, SourcePolicy, SourceStatus, serialize
from app.domain.policy import PolicyViolation
from app.domain.query_understanding import parse_query
from app.security import AdminPrincipal, AdminRole, require_role
from app.operational import Readiness, SlidingWindowRateLimiter


app = FastAPI(title="AI Procurement Search API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
catalog: Catalog = build_catalog()
public_rate_limiter = SlidingWindowRateLimiter(int(os.getenv("PUBLIC_RATE_LIMIT_PER_MINUTE", "120")))


@app.middleware("http")
async def apply_public_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/admin") or request.url.path in {"/health", "/ready", "/docs", "/openapi.json"}:
        return await call_next(request)
    client_key = request.client.host if request.client else "unknown"
    if not public_rate_limiter.allow(client_key):
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded; retry shortly"})
    return await call_next(request)


class SourceStatusChange(BaseModel):
    status: SourceStatus


class ImportRequest(BaseModel):
    source_id: str
    scope: str
    csv_contents: str = Field(min_length=1)


class PolicySubmission(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    allowed_scopes: list[str] = Field(min_length=1)
    allowed_domains: list[str] = Field(min_length=1)
    rate_budget_per_minute: int = Field(ge=1, le=1000)
    freshness_sla_hours: int = Field(ge=1, le=24 * 90)
    evidence_url: str

    def to_domain(self) -> SourcePolicy:
        if urlparse(self.evidence_url).scheme != "https":
            raise ValueError("evidence_url must be HTTPS")
        if any(urlparse(scope).scheme != "https" for scope in self.allowed_scopes):
            raise ValueError("every allowed scope must be an HTTPS URL")
        if any("/" in domain or ":" in domain for domain in self.allowed_domains):
            raise ValueError("allowed_domains must contain hostnames only")
        return SourcePolicy(
            version=self.version,
            approved=False,
            allowed_scopes=tuple(self.allowed_scopes),
            allowed_domains=tuple(domain.lower() for domain in self.allowed_domains),
            rate_budget_per_minute=self.rate_budget_per_minute,
            freshness_sla_hours=self.freshness_sla_hours,
            evidence_url=self.evidence_url,
            reviewed_at=datetime.now(UTC),
        )


class SourceRegistration(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    name: str = Field(min_length=2, max_length=160)
    base_url: str
    owner: str = Field(min_length=3, max_length=254)
    policy: PolicySubmission


class MatchReviewCreateRequest(BaseModel):
    offer_id: str
    candidate_product_id: str


class MatchReviewDecisionRequest(BaseModel):
    decision: MatchDecision
    reason: str = Field(min_length=3, max_length=1000)


class MouserLookupRequest(BaseModel):
    part_number: str = Field(min_length=1, max_length=128)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "catalog_backend": "postgres" if os.getenv("DATABASE_URL") else "memory"}


@app.get("/ready")
def ready() -> dict[str, object]:
    active_sources = sum(source.status is SourceStatus.ACTIVE for source in catalog.sources.values())
    readiness = Readiness(sources=len(catalog.sources), active_sources=active_sources, offers=len(catalog.offers))
    if not readiness.active_sources:
        raise HTTPException(status_code=503, detail="no active approved source is available")
    return {"status": "ready", "catalog": asdict(readiness)}


@app.get("/search")
def search(
    q: str = Query(min_length=1),
    quantity: int | None = Query(default=None, ge=1),
    category: str | None = None,
    manufacturer: str | None = None,
    price_status: PriceStatus | None = None,
    fresh_only: bool = False,
    parse_natural_language: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    query_plan = None
    effective_query, effective_quantity, max_price_inr = q, quantity, None
    if parse_natural_language and os.getenv("QUERY_PARSER_ENABLED", "false").lower() == "true":
        query_plan = parse_query(q)
        effective_query = query_plan.retrieval_query
        effective_quantity = quantity or query_plan.quantity
        max_price_inr = query_plan.max_price_inr
    try:
        all_groups = catalog.search(effective_query, effective_quantity, category, manufacturer, price_status, fresh_only, max_price_inr)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "query": q,
        "quantity": effective_quantity,
        "query_plan": query_plan.response() if query_plan else None,
        "applied_filters": {
            "category": category, "manufacturer": manufacturer,
            "price_status": price_status.value if price_status else None, "fresh_only": fresh_only,
            "max_price_inr": str(max_price_inr) if max_price_inr is not None else None,
        },
        "groups": all_groups[(page - 1) * page_size: page * page_size],
        "pagination": {"page": page, "page_size": page_size, "total_groups": len(all_groups)},
        "warnings": ["Results cover approved sources only. Price, tax, freight, and availability are never inferred."],
    }


@app.get("/search/facets")
def search_facets() -> dict[str, list[dict[str, object]]]:
    return catalog.search_facets()


@app.get("/products/{product_id}")
def product(product_id: str) -> dict[str, object]:
    try:
        return catalog.product_detail(product_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/offers/{offer_id}")
def offer(offer_id: str) -> object:
    try:
        return serialize(catalog.offer_detail(offer_id))
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/compare")
def compare(
    offer_id: list[str] = Query(min_length=2, max_length=5),
    quantity: int | None = Query(default=None, ge=1),
) -> dict[str, object]:
    try:
        return catalog.compare(offer_id, quantity)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/outbound/{offer_id}", status_code=302)
def outbound(offer_id: str, placement: str = "result", session_pseudonym: str | None = None) -> RedirectResponse:
    try:
        target = catalog.outbound(offer_id, placement, session_pseudonym)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PolicyViolation as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse(target, status_code=302)


@app.get("/admin/sources")
def list_sources(_principal: AdminPrincipal = Depends(require_role(AdminRole.VIEWER))) -> list[object]:
    return [serialize(source) for source in catalog.sources.values()]


@app.get("/admin/source-health")
def source_health(_principal: AdminPrincipal = Depends(require_role(AdminRole.VIEWER))) -> list[dict[str, object]]:
    return catalog.source_health()


@app.get("/admin/match-reviews")
def pending_match_reviews(_principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> list[object]:
    return [serialize(review) for review in catalog.pending_match_reviews()]


@app.post("/admin/match-reviews", status_code=201)
def create_match_review(request: MatchReviewCreateRequest, principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> object:
    try:
        return serialize(catalog.create_match_review(request.offer_id, request.candidate_product_id, principal.actor))
    except (NotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/match-reviews/{review_id}/decision")
def decide_match_review(review_id: str, request: MatchReviewDecisionRequest, principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> object:
    try:
        return serialize(catalog.decide_match_review(review_id, request.decision, request.reason, principal.actor))
    except (NotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/sources", status_code=201)
def register_source(request: SourceRegistration, principal: AdminPrincipal = Depends(require_role(AdminRole.SOURCE_APPROVER))) -> object:
    parsed_base_url = urlparse(request.base_url)
    if parsed_base_url.scheme != "https" or not parsed_base_url.hostname:
        raise HTTPException(status_code=422, detail="base_url must be an absolute HTTPS URL")
    try:
        policy = request.policy.to_domain()
        source = catalog.register_source(Source(
            id=request.id, name=request.name, base_url=request.base_url, owner=request.owner,
            status=SourceStatus.DRAFT, policy=None,
        ), actor=principal.actor)
        return serialize(catalog.set_source_policy(source.id, policy, principal.actor))
    except (ValueError, NotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/sources/{source_id}/policies")
def submit_policy(source_id: str, request: PolicySubmission, principal: AdminPrincipal = Depends(require_role(AdminRole.SOURCE_APPROVER))) -> object:
    try:
        return serialize(catalog.set_source_policy(source_id, request.to_domain(), principal.actor))
    except (ValueError, NotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/sources/{source_id}/policies/{version}/approve")
def approve_policy(source_id: str, version: str, principal: AdminPrincipal = Depends(require_role(AdminRole.SOURCE_APPROVER))) -> object:
    try:
        return serialize(catalog.approve_source_policy(source_id, version, principal.actor))
    except (ValueError, NotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/sources/{source_id}/status")
def set_source_status(source_id: str, change: SourceStatusChange, principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> object:
    try:
        return serialize(catalog.set_source_status(source_id, change.status, actor=principal.actor))
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/admin/imports")
def import_feed(request: ImportRequest, _principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> object:
    try:
        return serialize(catalog.import_csv(request.source_id, request.scope, request.csv_contents))
    except (NotFoundError, ValueError, PolicyViolation) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/mouser/lookups", status_code=201)
def mouser_lookup(request: MouserLookupRequest, _principal: AdminPrincipal = Depends(require_role(AdminRole.OPERATOR))) -> object:
    """Perform one policy-approved, quota-limited live Mouser part-number lookup."""
    if MOUSER_SOURCE_ID not in catalog.sources:
        raise HTTPException(status_code=409, detail="Mouser source must be registered and approved before live lookup")
    try:
        return serialize(configured_mouser_service(catalog).lookup_part_number(request.part_number))
    except (MouserError, RuntimeError, ValueError, PolicyViolation) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/admin/mouser/source-submissions", status_code=201)
def submit_mouser_source(principal: AdminPrincipal = Depends(require_role(AdminRole.SOURCE_APPROVER))) -> object:
    """Submit, but do not approve, the narrow read-only Mouser source policy."""
    if MOUSER_SOURCE_ID in catalog.sources:
        raise HTTPException(status_code=409, detail="Mouser source is already registered")
    source = Source(
        id=MOUSER_SOURCE_ID,
        name="Mouser Search API",
        base_url="https://api.mouser.com",
        owner="MCCIA procurement operations",
        status=SourceStatus.DRAFT,
        policy=None,
    )
    policy = SourcePolicy(
        version="mouser-search-v1",
        approved=False,
        allowed_scopes=(MOUSER_SCOPE,),
        allowed_domains=("www.mouser.com", "in.mouser.com"),
        rate_budget_per_minute=5,
        freshness_sla_hours=24,
        evidence_url="https://eu.mouser.com/en/api-search/",
    )
    catalog.register_source(source, actor=principal.actor)
    return serialize(catalog.set_source_policy(MOUSER_SOURCE_ID, policy, principal.actor))
