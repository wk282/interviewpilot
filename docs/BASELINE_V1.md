# InterviewPilot Baseline v1

Frozen on: 2026-07-17

## Purpose

Baseline v1 preserves the first complete end-to-end product version before the
Answer Critic, dynamic plan revision, multi-agent orchestration, and offline
evaluation work begins.

The Git tag for this snapshot is `baseline-v1`. Future work should be developed
on a separate branch. To inspect or restore this version later:

```powershell
git switch --detach baseline-v1
```

To continue development from the baseline without changing the tag:

```powershell
git switch -c restore/baseline-v1 baseline-v1
```

## Included Product Scope

- Personal and organization accounts, JWT authentication, workspaces, roles,
  and member invitations.
- Knowledge bases, PDF/Word/Markdown ingestion, parent-child chunking,
  embedding, indexing, retry, re-vectorization, and deletion.
- pgvector, PostgreSQL Trigram, OpenSearch BM25 weighted fusion, global
  Reranker, and parent-context restoration.
- LangGraph CRAG retrieval grading, query rewrite, Tavily fallback, local
  degradation, and trace recording.
- Job positions, resume profiles, job applications, resume snapshots, platform
  messaging, enterprise invitations, and interview decisions.
- Interview blueprint generation, one-question-at-a-time dynamic interviews,
  timeouts, asynchronous evidence-based evaluation, and evaluation retry.
- React/TypeScript/Ant Design frontend with Vite API proxying to FastAPI.

## AI Baseline

Prompt versions:

- Interview planner: `interview-blueprint-v3`
- Dynamic interviewer: `dynamic-interviewer-v1`
- CRAG retrieval: `crag-retrieval-v2`
- Interview evaluator: `evidence-evaluation-v1`

Retrieval defaults:

- Profile: `VECTOR_TRIGRAM_BM25_RERANK`
- Fusion weights: vector `0.50`, Trigram `0.10`, BM25 `0.40`
- Embedding dimensions: `1024`
- CRAG maximum rewrites: `1`
- CRAG maximum web searches: `1`

Model configuration is represented without credentials in
`backend/.env.example`. The real `backend/.env` is intentionally excluded from
Git.

## Runtime Components

- FastAPI: `8000`
- React/Vite: `5173`
- PostgreSQL/pgvector: `5432`
- Redis/Celery: `6379`
- OpenSearch: `9200`

Backend packages are pinned in `backend/requirements.txt`. Frontend packages
are locked by `frontend/package-lock.json`. Database schema history is
preserved in `backend/alembic/versions` through migration
`0013_interview_decisions`.

## Data Snapshot Boundary

The Git baseline contains source code, migrations, dependency manifests, and
safe configuration templates. It does not contain:

- `.env` secrets
- PostgreSQL records
- Redis task state
- OpenSearch index data
- `backend/data/uploads` documents
- logs or frontend build output

PostgreSQL and uploaded documents must be backed up separately if the current
test data must also be restorable. OpenSearch can be rebuilt from completed
document chunks; Redis is transient and should not be restored.

Suggested database backup command, to be run manually with the actual Docker
container and credentials:

```powershell
docker exec interviewpilot-postgres pg_dump -U interviewpilot -d interviewpilot -Fc -f /tmp/baseline-v1.dump
docker cp interviewpilot-postgres:/tmp/baseline-v1.dump .\backups\baseline-v1.dump
```

Copy `backend/data/uploads` to the same backup location if uploaded documents
must be preserved. Keep that backup outside Git because it can contain personal
data.

## Known Limitations

- Planner, interviewer, and evaluator are role-separated LLM services, not yet
  a strict multi-agent feedback system.
- The CRAG grader critiques retrieval evidence, not candidate answers.
- The initial interview plan is not revised during the interview.
- There is no automated offline benchmark or regression gate yet.
- Agent node latency, token usage, cost, and route decisions do not yet have a
  unified observability dashboard.

These limitations define the scope after Baseline v1; they are not defects to
backport into this tag.
