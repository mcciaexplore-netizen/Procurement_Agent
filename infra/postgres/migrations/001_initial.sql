CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE source_status AS ENUM ('draft', 'active', 'paused');
CREATE TYPE price_status AS ENUM ('public', 'quote_only', 'unknown');
CREATE TYPE match_decision AS ENUM ('approved', 'rejected', 'needs_review');

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  tier TEXT NOT NULL,
  status source_status NOT NULL DEFAULT 'draft',
  owner TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL REFERENCES sources(id),
  version TEXT NOT NULL,
  approved BOOLEAN NOT NULL DEFAULT false,
  allowed_scopes JSONB NOT NULL,
  allowed_domains JSONB NOT NULL,
  rate_budget_per_minute INTEGER NOT NULL CHECK (rate_budget_per_minute > 0),
  freshness_sla_hours INTEGER NOT NULL CHECK (freshness_sla_hours > 0),
  evidence_url TEXT NOT NULL,
  reviewed_at TIMESTAMPTZ NOT NULL,
  UNIQUE (source_id, version)
);

CREATE TABLE raw_captures (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL REFERENCES sources(id),
  request_url TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL,
  http_status INTEGER,
  content_hash CHAR(64) NOT NULL,
  object_key TEXT,
  parser_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sellers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_name TEXT,
  display_name TEXT NOT NULL,
  location TEXT,
  verification_level TEXT NOT NULL DEFAULT 'unverified',
  support_contact TEXT
);

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id TEXT,
  manufacturer TEXT,
  mpn TEXT,
  normalized_name TEXT NOT NULL,
  spec_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  lifecycle_status TEXT NOT NULL DEFAULT 'active'
);
CREATE UNIQUE INDEX products_manufacturer_mpn_key ON products (lower(manufacturer), mpn) WHERE mpn IS NOT NULL;
ALTER TABLE products ADD COLUMN search_document TSVECTOR GENERATED ALWAYS AS (
  to_tsvector('simple', coalesce(manufacturer, '') || ' ' || coalesce(mpn, '') || ' ' || normalized_name)
) STORED;
CREATE INDEX products_search_document_idx ON products USING GIN(search_document);

CREATE TABLE source_listings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL REFERENCES sources(id),
  external_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  raw_fields JSONB NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  UNIQUE (source_id, external_id),
  UNIQUE (source_id, canonical_url)
);

CREATE TABLE offers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_listing_id UUID NOT NULL REFERENCES source_listings(id),
  product_id UUID REFERENCES products(id),
  seller_id UUID REFERENCES sellers(id),
  price NUMERIC(18,4),
  currency CHAR(3),
  unit TEXT,
  pack_quantity INTEGER CHECK (pack_quantity IS NULL OR pack_quantity > 0),
  moq INTEGER CHECK (moq IS NULL OR moq > 0),
  quantity_breaks JSONB NOT NULL DEFAULT '[]'::jsonb,
  price_status price_status NOT NULL,
  tax_included BOOLEAN,
  shipping_included BOOLEAN,
  availability TEXT,
  observed_at TIMESTAMPTZ NOT NULL,
  raw_capture_id UUID NOT NULL REFERENCES raw_captures(id)
);
CREATE UNIQUE INDEX offers_source_listing_id_key ON offers(source_listing_id);
CREATE INDEX offers_product_id_idx ON offers(product_id);

CREATE TABLE spec_attributes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id),
  attribute_key TEXT NOT NULL,
  value_raw TEXT NOT NULL,
  value_normalized TEXT,
  unit TEXT,
  confidence NUMERIC(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE price_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id UUID NOT NULL REFERENCES offers(id),
  price NUMERIC(18,4),
  currency CHAR(3),
  unit TEXT,
  quantity_breaks JSONB NOT NULL DEFAULT '[]'::jsonb,
  observed_at TIMESTAMPTZ NOT NULL,
  change_reason TEXT NOT NULL
);

CREATE TABLE match_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_listing_id UUID NOT NULL REFERENCES source_listings(id),
  candidate_product_id UUID REFERENCES products(id),
  decision match_decision NOT NULL DEFAULT 'needs_review',
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  reason TEXT,
  reviewer TEXT,
  model_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);

CREATE TABLE outbound_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id UUID NOT NULL REFERENCES offers(id),
  session_pseudonym TEXT,
  placement TEXT NOT NULL,
  redirect_status INTEGER NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  before_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  after_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_entity_idx ON audit_events(entity_type, entity_id, occurred_at DESC);
