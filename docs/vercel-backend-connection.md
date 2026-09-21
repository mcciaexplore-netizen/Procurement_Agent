# Connecting the Vercel frontend to the API

Vercel can host the Next.js buyer interface, but `localhost:8000` refers to a
visitor's own computer. It cannot reach the FastAPI service running on a local
Docker Desktop installation.

Deploy `services/api` as a separate Docker web service on a container host,
using managed PostgreSQL and object storage for a real environment. The API
container initializes the initial schema once when it detects an empty database.
Then set these two values and redeploy the frontend:

For a Docker host, use the repository root as the build context and
`services/api/Dockerfile` as the Dockerfile path. This includes the initial
database migration in the API image.

1. In the API host, set `CORS_ORIGINS` to the exact Vercel frontend URL, for
   example `https://your-project.vercel.app`.
2. In Vercel Project Settings > Environment Variables, set
   `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS API URL, for example
   `https://procurement-api.example.com`. Do not use `localhost`.

The API host needs its own production secrets and infrastructure values:
`DATABASE_URL`, `RAW_CAPTURE_BACKEND=s3`, S3 bucket/credentials,
`ADMIN_API_TOKENS`, and `MOUSER_API_KEY`. Do not add any of these to Vercel's
frontend variables: `NEXT_PUBLIC_*` values are visible to browsers.

## Environment contract

| Location | Variable | Value |
| --- | --- | --- |
| Render API | `PORT` | `10000` |
| Render API | `CORS_ORIGINS` | Exact Vercel HTTPS origin, no trailing slash |
| Render API | `DATABASE_URL` | Render PostgreSQL internal connection string |
| Render API | `RAW_CAPTURE_BACKEND` | `s3` for persistent deployment storage |
| Render API | `S3_RAW_CAPTURE_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ENDPOINT_URL` | Managed S3-compatible storage values |
| Render API | `MOUSER_API_KEY` | Mouser secret, stored only in Render |
| Vercel frontend | `NEXT_PUBLIC_API_BASE_URL` | Public Render API HTTPS URL, no trailing slash |

After changing `NEXT_PUBLIC_API_BASE_URL`, redeploy the Vercel frontend because
Next.js embeds browser-visible variables during its build.
