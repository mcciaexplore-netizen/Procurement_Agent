# Connecting the Vercel frontend to the API

Vercel can host the Next.js buyer interface, but `localhost:8000` refers to a
visitor's own computer. It cannot reach the FastAPI service running on a local
Docker Desktop installation.

Deploy `services/api` as a separate Docker web service on a container host,
using managed PostgreSQL and object storage for a real environment. Then set
these two values and redeploy the frontend:

1. In the API host, set `CORS_ORIGINS` to the exact Vercel frontend URL, for
   example `https://your-project.vercel.app`.
2. In Vercel Project Settings > Environment Variables, set
   `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS API URL, for example
   `https://procurement-api.example.com`. Do not use `localhost`.

The API host needs its own production secrets and infrastructure values:
`DATABASE_URL`, `RAW_CAPTURE_BACKEND=s3`, S3 bucket/credentials,
`ADMIN_API_TOKENS`, and `MOUSER_API_KEY`. Do not add any of these to Vercel's
frontend variables: `NEXT_PUBLIC_*` values are visible to browsers.
