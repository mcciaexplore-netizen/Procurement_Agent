# Mouser live-data onboarding

This integration is deliberately limited to the read-only Mouser Search API.
It does not use Cart, Order, or Order History APIs, and it cannot create a
purchase or charge an account.

## 1. Store the key locally

Copy `.env.example` to `.env` and add the supplied key to `MOUSER_API_KEY`.
Keep `.env` outside version control and do not send the key in email, chat, or
screenshots. Because the first key was exposed in chat, revoke it in Mouser and
use its replacement for this step.

## 2. Start the application

Start the Docker stack from the repository root. The API receives the key only
as an environment variable; the browser never receives it.

## 3. Submit and approve the source policy

Using an approver token, submit the Mouser source at
`POST /admin/mouser/source-submissions`. Review the submitted policy, then
approve version `mouser-search-v1` through
`POST /admin/sources/mouser-search-api/policies/mouser-search-v1/approve`.

The approved scope allows only:

- `https://api.mouser.com/api/v1/search/partnumber`

The procurement service imposes a stricter internal safety budget than the
provider documents: five calls per minute and 100 calls per UTC day. Those
ceilings are hard-capped in code even if the environment values are changed.

## 4. Verify with one lookup

Use `POST /admin/mouser/lookups` with a known `part_number`. This makes one
read-only provider request and writes a content-hashed raw response plus the
normalised offers. It does not crawl the catalog. Search results then show the
source, observed time, public price facts, and a safe outbound product link.

## Operations

Pause the source immediately using the existing source status endpoint if data
quality, terms, or API errors require investigation. Rotate provider keys in
the secret store and restart the API; the application never returns a key in an
API response or error message.
