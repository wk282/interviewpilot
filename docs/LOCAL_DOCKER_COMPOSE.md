# Local Docker Compose

This Compose stack runs the complete InterviewPilot application locally:

- React static frontend behind Nginx
- FastAPI backend
- General Celery worker
- PostgreSQL with pgvector
- Redis
- OpenSearch
- Optional isolated PaddleOCR worker

On the first start of a new PostgreSQL volume, `backend/docker/init.sql`
creates the original eight foundation tables. Alembic then applies revisions
`0002` through the current head. Existing volumes do not rerun the init script.

## 1. Prepare configuration

The stack uses two environment files for different purposes:

- Root `.env`: Docker infrastructure settings such as ports and database password.
- `backend/.env`: model API keys and backend business settings.

Run from the repository root in PowerShell:

```powershell
Copy-Item .env.compose.example .env
Copy-Item backend/.env.example backend/.env
```

If `backend/.env` already contains working DeepSeek and embedding settings, keep it. Set a long random `JWT_SECRET_KEY`. The root database password should use URL-safe alphanumeric characters because it is embedded in connection URLs.

## 2. Start the default stack

Start Docker Desktop first, then run:

```powershell
docker compose up --build -d
docker compose ps
```

The first build downloads the base images and Python/npm dependencies. Open:

- Application: http://localhost:8080
- FastAPI documentation: http://localhost:8000/docs
- OpenSearch: http://localhost:9200

Follow startup and migration logs with:

```powershell
docker compose logs -f migrate backend celery-worker frontend
```

## 3. Enable scanned-PDF OCR

Set this in the root `.env`:

```text
OCR_WORKER_ENABLED=true
```

Then start the optional profile:

```powershell
docker compose --profile ocr up --build -d
docker compose logs -f ocr-worker
```

The OCR image is intentionally separate because PaddlePaddle pins dependencies that conflict with the main backend environment. Its first task also downloads PaddleOCR models, so the first OCR request is slower.

## 4. Stop and preserve data

```powershell
docker compose down
```

This removes containers and networks but keeps PostgreSQL, Redis, OpenSearch, uploads, logs, and OCR model volumes.

Do not add `-v` unless all local Compose data should be deleted:

```powershell
docker compose down -v
```

## 5. Existing database data

The Compose PostgreSQL volume starts as a new database. Existing data from another PostgreSQL container is not copied automatically. Restore a dump after the stack starts, for example:

```powershell
docker compose cp "D:\path\baseline-v1.dump" postgres:/tmp/baseline-v1.dump
docker compose exec postgres pg_restore --clean --if-exists --no-owner --no-privileges -U interviewpilot -d interviewpilot /tmp/baseline-v1.dump
docker compose run --rm migrate
```

Use the actual dump path and database values from the root `.env`. Back up the current database before attempting a restore.

## 6. Useful diagnostics

```powershell
docker compose ps
docker compose logs --tail=200 backend
docker compose logs --tail=200 celery-worker
docker compose exec postgres pg_isready -U interviewpilot -d interviewpilot
docker compose exec redis redis-cli ping
```
