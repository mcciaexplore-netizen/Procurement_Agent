# Implementation status: vertical slice 01

## Product interpretation

The project is a procurement discovery and comparison layer. Its trust proposition is not broad web coverage; it is accurate, attributable, current offers from approved sources. It must link buyers to original sellers and must never imply custody of payment, inventory, logistics, or seller identity.

## Delivered in this slice

| Plan capability | Implemented behaviour |
| --- | --- |
| Source policy registry | Source status plus immutable-style versioned policy data with allowed feed scopes, domains, rate budget, freshness SLA, evidence URL, and approval flag. Draft sources cannot run; an approver must activate the submitted policy. Admin API routes are role-gated bootstrap controls. |
| Connector #1 | CSV feed importer that refuses inactive, unapproved, or out-of-scope source runs. |
| Connector #2 | Read-only Mouser Search API part-number adapter. It captures the raw provider response, imports source facts only after source-policy approval, and hard-caps requests at five/minute and 100/day. Cart, order, and account APIs are not present. |
| Multi-source comparison | A second permitted feed fixture exercises exact-MPN grouping and cross-source price/MOQ comparison; pausing one source leaves approved alternatives discoverable. |
| Raw capture and replay | Hashes every feed body, records capture metadata, and has deterministic row processing. |
| Raw-capture storage | Stores feed bodies immutably by SHA-256 object key in local development or an S3/MinIO-compatible bucket; database captures retain the pointer for replay. |
| Normalization | Preserves the commercial unknown state; parses MPN, price status, unit, MOQ, pack quantity, availability, and currency. |
| Quantity pricing | Parses non-overlapping source-declared quantity breaks and applies the eligible tier in search and comparison without estimating price. |
| Commercial completeness | Tax and shipping inclusion are stored as explicit true/false/unknown supplier facts; ambiguous values are rejected. |
| Query understanding | Behind a feature flag, extracts explicit quantity, INR budget, and location terms into an inspectable plan; original-query retrieval remains the safe fallback. |
| Matching | Manufacturer + MPN key creates a canonical product family. There is no fuzzy auto-merge. |
| Search and ranking | MPN-first / token retrieval with policy, freshness, availability, and price-basis reason codes. |
| Structured filters | Live category, manufacturer, public/quote/unknown price status, and fresh-only facets are applied after retrieval without dropping offer provenance. |
| Comparison | Compares two to five offers for one canonical product, suppresses numeric price badges when price bases conflict, and labels MOQ, freshness, and quote-only outcomes. |
| Match review | Operators can create and decide an auditable review for a possible product match. Candidate features are recorded; no fuzzy merge is applied automatically. |
| Freshness | Fresh, aging, stale, and source-unavailable labels; stale or paused source offers are withheld from results. |
| Safe click-out | Only a registered HTTPS source-domain redirect is issued, and a minimal outbound event is created. |
| Audit trail | Source pause/resume creates an actor-attributed audit event that persists with the catalog. |
| Maintenance | A one-shot freshness worker reports fresh/aging/stale counts and records an audit checkpoint, ready for cron or a queue scheduler. |
| Source health | The admin plane reports source-level capture volume, offer counts, freshness, public-price and commercial-field completeness, outbound events, and redirect failures. |
| Quality gate | Fixture-backed exact-MPN, quote-only, and material-identifier benchmarks run with the domain suite in GitHub Actions. |
| Data foundation | PostgreSQL adapter persists and reloads sources, policy versions, captures, products, offers, and outbound events when `DATABASE_URL` is configured. In-memory mode remains for tests and a no-infrastructure demo. |

## Deliberate non-implementation

- No crawler, proxy, CAPTCHA handling, logged-in marketplace access, or automated source discovery.
- No production SSO/OIDC, managed secret store, queue, background scheduler, or deployed infrastructure.
- No automatic fuzzy product merging, substitutes labelled as drop-in, landed-cost calculations, or invented commercial facts.
- No LLM query parser. The plan correctly puts this behind a later feature flag after deterministic search and benchmarks.

## Acceptance evidence

The test suite verifies exact MPN grouping with provenance, quote-only behavior, source pausing, source allow-list redirects, idempotent feed import, Mouser response mapping, and its daily quota boundary. Docker Compose configuration validates successfully. The Docker Hub DNS issue must still be resolved before images can be pulled and the container runtime can be verified.

## Recommended next increment

Rotate the exposed provider key, add its replacement to the local environment, submit and approve the Mouser policy, then perform one live part-number lookup. Production deployment then needs SSO/OIDC, managed secrets, managed PostgreSQL/object storage, scheduled freshness monitoring, HTTPS/WAF, backups, and an India-qualified legal review.
