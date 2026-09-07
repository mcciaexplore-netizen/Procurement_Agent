# AI Procurement Search Engine

A permission-first procurement discovery and comparison service for Indian manufacturing buyers. It helps buyers find and compare supplier offers, then sends them to the original seller. It is **not** a checkout, marketplace-crawling, or autonomous purchasing system.

## What is implemented in this foundation

- Source-policy gate: imports run only for active sources with an approved policy and an allowed scope.
- Immutable raw-capture metadata and idempotent CSV feed imports.
- Deterministic normalization for MPNs, source-declared quantity-price tiers, MOQ, currency, unit, and freshness.
- Explicit tax and shipping-inclusion states, preserved as `true`, `false`, or `unknown` without estimates.
- Exact MPN product grouping, transparent ranking, quote-only support, and buyer-facing category/manufacturer/price-status/freshness filters.
- Two-to-five-offer comparison with quantity eligibility, compatible price-basis checks, and explainable badges.
- Search, product, offer, admin-source, import, and safe outbound-redirect API routes.
- Two approved supplier-feed fixtures, a strict CSV connector contract, and focused unit tests.
- Role-gated source registration and policy-approval endpoints, plus a source-operations page at `/admin`.
- Source-health reporting for offer freshness, field completeness, capture volume, outbound volume, and redirect failures.
- A human-review API for ambiguous product matches and a controlled search benchmark suite enforced in CI.
- Feature-flagged deterministic query understanding for explicit quantity, INR budget, and location signals; this is the safe contract for a later schema-constrained AI parser.
- PostgreSQL-backed persistence (when `DATABASE_URL` is set), Docker Compose topology, contracts, and a minimal Next.js web shell.
- Immutable local or S3/MinIO raw-capture storage and a one-shot freshness-sweep worker. Docker Compose provisions a MinIO bucket for local multi-service development.
- A read-only Mouser Search API adapter that imports live part-number results only after an approver enables its narrowly scoped source policy. It has hard safety ceilings of five calls/minute and 100 calls/day.

## Safety and data policy

Only ingest partner APIs, feeds, supplier uploads, or explicitly approved public scopes. Never bypass CAPTCHAs, login walls, robots directives, rate limits, or source terms. Every displayed offer must retain its source URL, source name, observation time, and price-status. The redirect endpoint only targets registered source domains.

## Run locally

The API has FastAPI runtime dependencies listed in `services/api/requirements.txt`. Install them into a virtual environment, then run:

```powershell
cd services/api
uvicorn app.main:app --reload --port 8000
```

The development API seeds approved fixture sources for demonstration. Open `http://localhost:8000/docs` for OpenAPI documentation. Run the domain tests with:

```powershell
cd services/api
python -m pytest tests
```

For the intended service topology, use `docker compose up --build`. The included compose file is a local-development topology; production must use managed secrets, storage, PostgreSQL backups, HTTPS/WAF, and an India-qualified legal review before live source onboarding.

For the complete startup, verification, and teardown sequence, see [docs/setup.md](docs/setup.md).

Admin endpoints require `X-Admin-Token`. Docker Compose supplies the development-only value `local-development-change-me`; set a unique secret through deployment configuration in every other environment. `ADMIN_API_TOKENS` can define comma-separated `viewer:token`, `operator:token`, and `source_approver:token` roles. `X-Actor` is recorded in audit events and must be supplied by the authenticated identity layer once SSO/OIDC is added.

Run scheduled maintenance once (for a scheduler or CI job) with `python -m worker.run --job stale-offer-sweep`. It reports fresh/aging/stale offer counts and writes an audit checkpoint; it does not crawl or contact a source.

For the controlled live Mouser setup, source-policy approval, quota limits, and verification flow, see [docs/mouser-onboarding.md](docs/mouser-onboarding.md).

## Repository layout

```text
apps/web/                  Next.js buyer UI shell
services/api/              FastAPI catalog, policy, search, and redirect API
services/worker/           feed-import worker entry point
packages/contracts/        versioned event contracts
packages/source-connectors/sample_feed/
                           approved-feed connector fixture
infra/postgres/migrations/ database schema
docs/                      operational and source-policy documentation
```

## Next build milestones

1. Add authenticated admin roles, immutable audit persistence, per-source rate limits, and worker scheduling.
2. Move raw feed bodies to object storage, retaining only immutable pointers in PostgreSQL.
3. Add search-index publishing and the comparison tray UI.
4. Add a second production source only after documented permission and adapter contract tests.
5. Add schema-constrained AI query parsing behind a feature flag, with lexical fallback.
