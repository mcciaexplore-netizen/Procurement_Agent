# Sample-feed connector

This connector represents a signed or supplier-submitted CSV catalog feed. It has no network fetch capability: callers supply the feed bytes only after source-policy approval.

The canonical fields are `external_id`, `canonical_url`, `title`, `price`, and `seller_name`, with optional `manufacturer`, `mpn`, `category`, `currency`, `unit`, `pack_quantity`, `moq`, and `availability`. Every import persists a raw-capture hash before deterministic normalization.
