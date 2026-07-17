# InterviewPilot

InterviewPilot is a resume-driven technical interview platform built around an
Agentic CRAG workflow.

## Repository Layout

```text
ResearchPilot/
|- backend/                       FastAPI, Celery, AI services and migrations
|  |- app/                        Backend application package
|  |- alembic/                    Database migrations
|  |- data/                       Backend datasets and runtime documents
|  |- .env.example                Backend configuration template
|  |- alembic.ini
|  |- requirements.txt
|  `- run_server.py
|- frontend/                      React, TypeScript and Vite application
|- docs/                          Architecture and baseline documentation
|- 面试题/                         Source question-bank materials
`- docker-compose.opensearch.yml  OpenSearch development dependency
```

## Backend

Run backend commands from the `backend` directory so `.env`, Alembic, uploaded
documents, and logs resolve to the expected paths.

```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn run_server:app --reload --host 0.0.0.0 --port 8000
```

Run the Windows Celery worker in a separate terminal:

```powershell
cd backend
celery -A app.workers.celery_app.celery_app worker --loglevel=info --pool=solo
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/api` to the backend at
`http://127.0.0.1:8000`.

## Baseline

The complete pre-evaluation product version is preserved by Git tag
`baseline-v1`. See `docs/BASELINE_V1.md` for its scope and restoration notes.
