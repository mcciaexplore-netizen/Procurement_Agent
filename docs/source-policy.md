# Source policy gate

No connector may publish or even fetch a source until an authorised administrator records an approved policy version.

Required policy evidence:

- source owner and technical contact;
- access method (partner API, signed feed, supplier upload, or explicitly permitted public scope);
- terms and robots evidence URLs, review date, and allowed URL/feed scopes;
- rate and concurrency budget;
- attribution text and rights decision for every displayable field;
- freshness SLA and expiry action;
- explicit go/no-go decision.

Stop and pause the connector on a 403, CAPTCHA, login wall, robots disallow, explicit rate-limit signal, policy expiry, or a material parser-quality regression. Do not add proxies, credentials, or retry behaviour to evade the stop condition.

The sample source in this repository is a local fixture representing a cooperative supplier feed. It is not permission to ingest any real supplier or marketplace.
