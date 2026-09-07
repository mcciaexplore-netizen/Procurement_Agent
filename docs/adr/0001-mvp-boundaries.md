# ADR 0001: Start with a controlled feed vertical slice

## Decision

Build the first vertical slice around a cooperative CSV/feed importer, exact manufacturer-part-number (MPN) grouping, explicit price-basis fields, and link-out comparison. The deployment shape is a modular monolith API with separate worker entry points.

## Why

This tests procurement usefulness without treating public availability as reuse permission. Exact MPNs are deterministic enough to establish a quality benchmark and leave ambiguous product matching to a later review queue.

## Consequences

- The initial catalog is intentionally small and source-approved.
- Search is structured and lexical; an LLM cannot invent catalog facts or prices.
- Persistence and object storage are represented by a PostgreSQL schema and adapter seam, while this first slice uses in-memory state for an executable, dependency-light demo.
