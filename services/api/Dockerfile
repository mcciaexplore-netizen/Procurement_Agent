FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/ .
COPY infra/postgres/migrations /infra/postgres/migrations
ENV MIGRATION_PATH=/infra/postgres/migrations/001_initial.sql
EXPOSE 8000
CMD ["sh", "-c", "python -m app.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
