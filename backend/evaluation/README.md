# InterviewPilot Offline Evaluation

This directory freezes the evaluation corpus and annotations used to compare retrieval,
CRAG routing, and interview Critic behavior. Generated reports and environment-specific
document IDs are intentionally excluded from Git.

## Assets

- `fixtures/documents/`: 12 frozen Markdown documents from the AI application and Agent question banks.
- `manifests/corpus_v1.json`: source paths, fixture names, and SHA256 checksums.
- `datasets/retrieval_v1.jsonl`: 30 manually rewritten retrieval queries with graded relevance.
- `datasets/interview_turn_v1.jsonl`: 20 Critic regression cases.
- `datasets/critic_predictions.example.jsonl`: prediction schema example only.
- `metrics/`: deterministic retrieval and Critic metrics.
- `reports/`: generated JSON, CSV, and Markdown reports; only `.gitkeep` is committed.

Run all commands from `backend`. These commands execute project code and must be run
manually when the API, worker, PostgreSQL, Redis, and OpenSearch are ready.

## 1. Verify Frozen Assets

```powershell
python -m evaluation.runner verify
```

This checks source and fixture hashes, canonical question IDs, retrieval annotations,
and Critic labels. It does not call a model or database.

## 2. Prepare the Evaluation Knowledge Base

Set a short-lived access token without committing it:

```powershell
$env:EVAL_ACCESS_TOKEN = "your-access-token"
```

For a personal workspace:

```powershell
python -m evaluation.runner prepare --workspace-id YOUR_WORKSPACE_ID
```

For an organization workspace:

```powershell
python -m evaluation.runner prepare --workspace-id YOUR_WORKSPACE_ID --purpose TECHNICAL_STANDARD --visibility WORKSPACE
```

The command creates or reuses `Evaluation Corpus v1`, uploads the frozen fixtures, waits
for ingestion, and writes `manifests/document_mapping_v1.json`. That mapping belongs to
the current database environment and must not be committed.

## 3. Run Retrieval Evaluation

Default comparison:

```powershell
python -m evaluation.runner run
```

All eight retrieval profiles plus local CRAG:

```powershell
python -m evaluation.runner run --all-profiles --include-crag
```

Include Tavily fallback only when web search configuration and cost are acceptable:

```powershell
python -m evaluation.runner run --all-profiles --include-crag --include-crag-web
```

Each run stores:

- MRR, Hit@K, Recall@K, and NDCG@K for K = 1, 3, 5, 10.
- Mean and p95 latency, result count, and failure count.
- CRAG rewrite rate, web-search rate, and final grade distribution.
- Per-query retrieved chunks and complete CRAG Trace.
- Runtime model names, embedding dimensions, prompt versions, fusion weights, and CRAG limits.

Web results remain in the Trace but are excluded from local corpus relevance scores.

## 4. Score Critic Predictions

Export exactly one JSON object per `case_id` from the Critic under test:

```json
{"case_id":"turn-001","score":90,"next_action":"INCREASE_DIFFICULTY","difficulty_delta":1,"knowledge_gaps":[]}
```

The prediction file must cover all 20 cases exactly once. Then run:

```powershell
python -m evaluation.runner score-critic --predictions path\to\critic_predictions.jsonl
```

Metrics cover score interval compliance, next-action accuracy, difficulty accuracy, and
knowledge-gap precision, recall, F1, and exact match. Reports are also grouped by competency.

## 5. Rebuild Retrieval Reports

To regenerate CSV and Markdown from an existing raw result without repeating retrieval:

```powershell
python -m evaluation.runner report --input evaluation\reports\RUN_ID\results.json
```

## Versioning Rule

Do not edit a published `v1` corpus or annotation in place. Add a new manifest/dataset
version so baseline and optimized branches remain directly comparable.
