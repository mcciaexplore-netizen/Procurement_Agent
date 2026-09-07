# Local setup and verification

## Prerequisites

- Docker Desktop with Linux containers enabled and access to Docker Hub.
- Optional: Python 3.12 for the fast domain-test path.

If Docker cannot resolve `registry-1.docker.io`, configure its proxy/DNS first. The project cannot download PostgreSQL, Redis, MinIO, Node, or Python images until that is working.

## Start the full stack

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

The startup sequence provisions PostgreSQL, Redis, MinIO, the `procurement-raw-captures` bucket, API, worker, and the Next.js web app.

## Verify the running services

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl "http://localhost:8000/search?q=STM32F407VGT6&quantity=250"
```

Try the feature-flagged smart-query contract with:

```powershell
curl "http://localhost:8000/search?q=STM32F407VGT6%20quantity%20500%20under%20Rs%20425&parse_natural_language=true"
```

The response includes the parsed plan and applies a budget only where INR prices and quantity tiers are actually comparable.

- Buyer app: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

The default development admin token is `local-development-change-me` as defined in `docker-compose.yml`. Send it only as the `X-Admin-Token` request header. Do not use it outside local development.

## Run the quality suite

```powershell
$env:PYTHONPATH = (Resolve-Path services/api).Path
python -m pytest services/api/tests -q
```

## Stop the local stack

```powershell
docker compose down
```

This keeps named database and object-storage volumes. To reset local data intentionally, use `docker compose down -v`; this permanently removes local development data.
