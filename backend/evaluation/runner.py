from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from evaluation.corpus import (
    EVALUATION_ROOT,
    FIXTURE_ROOT,
    corpus_question_index,
    freeze_sources,
    load_manifest,
    resolve_canonical_id,
    verify_fixtures,
    verify_sources,
)
from evaluation.metrics import (
    aggregate_critic_metrics,
    aggregate_metrics,
    evaluate_critic_prediction,
    evaluate_query,
)


DATASET_PATH = EVALUATION_ROOT / "datasets" / "retrieval_v1.jsonl"
CRITIC_DATASET_PATH = EVALUATION_ROOT / "datasets" / "interview_turn_v1.jsonl"
MAPPING_PATH = EVALUATION_ROOT / "manifests" / "document_mapping_v1.json"
REPORT_ROOT = EVALUATION_ROOT / "reports"
DEFAULT_PROFILES = [
    "VECTOR",
    "VECTOR_RERANK",
    "VECTOR_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25_RERANK",
]
ALL_PROFILES = [
    "VECTOR",
    "VECTOR_TRIGRAM",
    "VECTOR_RERANK",
    "VECTOR_TRIGRAM_RERANK",
    "VECTOR_BM25",
    "VECTOR_BM25_RERANK",
    "VECTOR_TRIGRAM_BM25",
    "VECTOR_TRIGRAM_BM25_RERANK",
    "VECTOR_BM25_RRF",
    "VECTOR_BM25_RRF_RERANK",
    "VECTOR_TRIGRAM_BM25_RRF",
    "VECTOR_TRIGRAM_BM25_RRF_RERANK",
]

CUTOFFS = (1, 3, 5, 10)
CRITIC_ACTIONS = {
    "FOLLOW_UP",
    "INCREASE_DIFFICULTY",
    "DECREASE_DIFFICULTY",
    "SWITCH_TOPIC",
    "END_INTERVIEW",
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
    return rows


def validate_dataset(dataset: list[dict], question_index: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(dataset, start=1):
        query_id = str(row.get("query_id", "")).strip()
        query = str(row.get("query", "")).strip()
        relevance = row.get("relevance")
        if not query_id:
            errors.append(f"row {row_number}: missing query_id")
        elif query_id in seen_ids:
            errors.append(f"row {row_number}: duplicate query_id {query_id}")
        seen_ids.add(query_id)
        if len(query) < 8:
            errors.append(f"{query_id}: query is too short")
        if not isinstance(relevance, dict) or not relevance:
            errors.append(f"{query_id}: relevance must be a non-empty object")
            continue
        for canonical_id, grade in relevance.items():
            if canonical_id not in question_index:
                errors.append(f"{query_id}: unknown relevance id {canonical_id}")
            if not isinstance(grade, int) or not 1 <= grade <= 3:
                errors.append(f"{query_id}: relevance grade must be 1..3 for {canonical_id}")
    return errors


def validate_critic_dataset(dataset: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(dataset, start=1):
        case_id = str(row.get("case_id", "")).strip()
        gold = row.get("gold")
        if not case_id:
            errors.append(f"row {row_number}: missing case_id")
        elif case_id in seen_ids:
            errors.append(f"row {row_number}: duplicate case_id {case_id}")
        seen_ids.add(case_id)
        if not str(row.get("question", "")).strip():
            errors.append(f"{case_id}: missing question")
        if not str(row.get("answer", "")).strip():
            errors.append(f"{case_id}: missing answer")
        if not isinstance(gold, dict):
            errors.append(f"{case_id}: gold must be an object")
            continue
        score_range = gold.get("score_range")
        if (
            not isinstance(score_range, list)
            or len(score_range) != 2
            or not all(isinstance(value, (int, float)) for value in score_range)
            or score_range[0] > score_range[1]
        ):
            errors.append(f"{case_id}: score_range must be [minimum, maximum]")
        if gold.get("next_action") not in CRITIC_ACTIONS:
            errors.append(f"{case_id}: unsupported next_action")
        if gold.get("difficulty_delta") not in {-1, 0, 1}:
            errors.append(f"{case_id}: difficulty_delta must be -1, 0, or 1")
        if not isinstance(gold.get("knowledge_gaps", []), list):
            errors.append(f"{case_id}: knowledge_gaps must be a list")
    return errors


def validate_critic_predictions(dataset: list[dict], predictions: list[dict]) -> list[str]:
    errors: list[str] = []
    expected_ids = {row["case_id"] for row in dataset}
    seen_ids: set[str] = set()
    for row_number, row in enumerate(predictions, start=1):
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            errors.append(f"prediction row {row_number}: missing case_id")
            continue
        if case_id in seen_ids:
            errors.append(f"prediction row {row_number}: duplicate case_id {case_id}")
        seen_ids.add(case_id)
        if case_id not in expected_ids:
            errors.append(f"prediction row {row_number}: unknown case_id {case_id}")
        try:
            score = float(row.get("score"))
            if not 0 <= score <= 100:
                errors.append(f"{case_id}: score must be between 0 and 100")
        except (TypeError, ValueError):
            errors.append(f"{case_id}: score must be numeric")
        if row.get("next_action") not in CRITIC_ACTIONS:
            errors.append(f"{case_id}: unsupported next_action")
        if row.get("difficulty_delta") not in {-1, 0, 1}:
            errors.append(f"{case_id}: difficulty_delta must be -1, 0, or 1")
        if not isinstance(row.get("knowledge_gaps", []), list):
            errors.append(f"{case_id}: knowledge_gaps must be a list")
    missing = expected_ids - seen_ids
    if missing:
        errors.append(f"predictions are missing case IDs: {sorted(missing)}")
    return errors


def api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def find_or_create_knowledge_base(
    client: httpx.AsyncClient,
    workspace_id: str,
    token: str,
    name: str,
    purpose: str,
    visibility: str,
) -> dict:
    path = f"/workspaces/{workspace_id}/knowledge-bases"
    response = await client.get(path, headers=api_headers(token))
    response.raise_for_status()
    existing = next((item for item in response.json() if item["name"] == name), None)
    if existing:
        return existing
    response = await client.post(
        path,
        headers=api_headers(token),
        json={
            "name": name,
            "purpose": purpose,
            "visibility": visibility,
        },
    )
    response.raise_for_status()
    return response.json()


async def prepare_corpus(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    freeze_sources(manifest)
    mapping = {
        "corpus_id": manifest["corpus_id"],
        "workspace_id": args.workspace_id,
        "knowledge_base_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": {},
    }
    async with httpx.AsyncClient(base_url=args.api_base, timeout=args.timeout) as client:
        knowledge_base = await find_or_create_knowledge_base(
            client,
            args.workspace_id,
            args.token,
            args.knowledge_base_name,
            args.purpose,
            args.visibility,
        )
        mapping["knowledge_base_id"] = knowledge_base["id"]
        documents_path = (
            f"/workspaces/{args.workspace_id}/knowledge-bases/{knowledge_base['id']}/documents"
        )
        response = await client.get(documents_path, headers=api_headers(args.token))
        response.raise_for_status()
        existing_by_filename = {
            item["original_filename"]: item for item in response.json()
        }

        for source in manifest["sources"]:
            filename = source["fixture_filename"]
            document = existing_by_filename.get(filename)
            if document is not None and document["file_hash"] != source["sha256"]:
                raise ValueError(
                    f"Existing evaluation document has unexpected content: {filename}"
                )
            if document is None:
                with (FIXTURE_ROOT / filename).open("rb") as stream:
                    response = await client.post(
                        documents_path,
                        headers=api_headers(args.token),
                        files={"file": (filename, stream, "text/markdown")},
                    )
                response.raise_for_status()
                document = response.json()
                print(f"uploaded {source['source_id']} -> {document['id']}")
            else:
                print(f"reused {source['source_id']} -> {document['id']}")
            mapping["documents"][source["source_id"]] = {
                "document_id": document["id"],
                "filename": filename,
                "status": document["status"],
                "ingestion_status": document["ingestion_status"],
            }

        if args.wait:
            deadline = time.monotonic() + args.wait_timeout
            while time.monotonic() < deadline:
                response = await client.get(documents_path, headers=api_headers(args.token))
                response.raise_for_status()
                current = {item["id"]: item for item in response.json()}
                statuses = []
                for item in mapping["documents"].values():
                    document = current[item["document_id"]]
                    item["status"] = document["status"]
                    item["ingestion_status"] = document["ingestion_status"]
                    statuses.append(document["ingestion_status"])
                if all(status == "COMPLETED" for status in statuses):
                    break
                failed = [status for status in statuses if status in {"FAILED", "CANCELLED"}]
                if failed:
                    raise RuntimeError(f"Corpus ingestion failed: {statuses}")
                print(f"waiting for ingestion: {statuses.count('COMPLETED')}/{len(statuses)}")
                await asyncio.sleep(args.poll_interval)
            else:
                raise TimeoutError("Timed out waiting for corpus ingestion")

    MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAPPING_PATH.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"mapping written to {MAPPING_PATH}")


def load_mapping() -> dict:
    if not MAPPING_PATH.is_file():
        raise FileNotFoundError(f"Missing {MAPPING_PATH}; run prepare first")
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def validate_mapping(mapping: dict, manifest: dict) -> list[str]:
    errors: list[str] = []
    if mapping.get("corpus_id") != manifest["corpus_id"]:
        errors.append("document mapping corpus_id does not match corpus manifest")
    expected = {source["source_id"] for source in manifest["sources"]}
    actual = set(mapping.get("documents", {}))
    if actual != expected:
        errors.append(
            f"document mapping sources differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )
    document_ids = [
        item.get("document_id") for item in mapping.get("documents", {}).values()
    ]
    if len(document_ids) != len(set(document_ids)):
        errors.append("document mapping contains duplicate document IDs")
    not_ready = [
        source_id
        for source_id, item in mapping.get("documents", {}).items()
        if item.get("ingestion_status") != "COMPLETED"
    ]
    if not_ready:
        errors.append(f"evaluation documents are not ready: {not_ready}")
    return errors


def map_results(results: list[dict], mapping: dict, question_index: dict[str, dict]) -> list[dict]:
    source_by_document = {
        item["document_id"]: source_id
        for source_id, item in mapping["documents"].items()
    }
    mapped: list[dict] = []
    for result in results:
        source_id = source_by_document.get(str(result.get("document_id")))
        canonical_id = resolve_canonical_id(
            source_id,
            str(result.get("child_content", "")),
            str(result.get("context", "")),
            question_index,
        )
        mapped.append(
            {
                "canonical_id": canonical_id,
                "source_id": source_id,
                "document_id": str(result.get("document_id", "")),
                "chunk_id": str(result.get("chunk_id", "")),
                "fusion_rank": result.get("fusion_rank"),
                "rerank_rank": result.get("rerank_rank"),
                "fusion_score": result.get("fusion_score"),
                "rerank_score": result.get("rerank_score"),
                "retrieval_sources": result.get("retrieval_sources", []),
                "preview": str(result.get("child_content", ""))[:300],
            }
        )
    return mapped


async def retrieve_profile(
    client: httpx.AsyncClient,
    mapping: dict,
    token: str,
    query: str,
    profile: str,
    top_k: int,
) -> dict:
    path = (
        f"/workspaces/{mapping['workspace_id']}/knowledge-bases/"
        f"{mapping['knowledge_base_id']}/retrieval/search"
    )
    response = await client.post(
        path,
        headers=api_headers(token),
        json={"query": query, "top_k": top_k, "profile": profile},
    )
    response.raise_for_status()
    return response.json()


async def retrieve_crag(
    client: httpx.AsyncClient,
    mapping: dict,
    token: str,
    query: str,
    profile: str,
    top_k: int,
    web_enabled: bool,
) -> tuple[dict, dict]:
    from app.services.crag_workflow import CRAGWorkflow

    async def provider(rewritten_query: str) -> list[dict]:
        response = await retrieve_profile(
            client, mapping, token, rewritten_query, profile, top_k
        )
        return [
            {
                "evidence_id": index,
                "content": item["context"],
                **item,
            }
            for index, item in enumerate(response["results"], start=1)
        ]

    workflow = CRAGWorkflow(
        None,
        None,
        None,
        None,
        None,
        retrieval_provider=provider,
        web_enabled_override=web_enabled,
        retrieval_profile=profile,
    )
    result = await workflow.run(query)
    local_evidence = [item for item in result.evidence if item.get("source_type") != "WEB"]
    return {"results": local_evidence}, {"grade": result.grade, "trace": result.trace}


def aggregate_crag_routes(rows: list[dict]) -> dict[str, float | int]:
    completed = [
        row
        for row in rows
        if row.get("status") == "COMPLETED" and isinstance(row.get("crag"), dict)
    ]
    if not completed:
        return {"crag_case_count": 0}

    rewrite_count = 0
    web_search_count = 0
    model_grade_count = 0
    fallback_grade_count = 0
    empty_evidence_grade_count = 0
    fallback_case_count = 0
    grader_call_count = 0
    grade_counts = {"sufficient": 0, "partial": 0, "irrelevant": 0, "unknown": 0}
    for row in completed:
        crag = row["crag"]
        nodes = {
            event.get("node")
            for event in crag.get("trace", [])
            if isinstance(event, dict)
        }
        rewrite_count += int("rewrite_query" in nodes)
        web_search_count += int("web_search" in nodes)
        grader_events = [
            event
            for event in crag.get("trace", [])
            if isinstance(event, dict) and event.get("node") == "retrieval_grader"
        ]
        grading_sources = [event.get("grading_source") for event in grader_events]
        grader_call_count += len(grading_sources)
        model_grade_count += grading_sources.count("model")
        fallback_grade_count += grading_sources.count("fallback_rule")
        empty_evidence_grade_count += grading_sources.count("empty_evidence_rule")
        fallback_case_count += int("fallback_rule" in grading_sources)
        status = str(crag.get("grade", {}).get("status", "unknown")).lower()
        grade_counts[status if status in grade_counts else "unknown"] += 1

    count = len(completed)
    return {
        "crag_case_count": count,
        "crag_rewrite_rate": round(rewrite_count / count, 6),
        "crag_web_search_rate": round(web_search_count / count, 6),
        "crag_grader_call_count": grader_call_count,
        "crag_model_grader_call_rate": round(
            model_grade_count / grader_call_count, 6
        ) if grader_call_count else 0.0,
        "crag_fallback_grader_call_rate": round(
            fallback_grade_count / grader_call_count, 6
        ) if grader_call_count else 0.0,
        "crag_empty_evidence_rule_call_rate": round(
            empty_evidence_grade_count / grader_call_count, 6
        ) if grader_call_count else 0.0,
        "crag_fallback_case_rate": round(fallback_case_count / count, 6),
        **{
            f"crag_grade_{status}_rate": round(value / count, 6)
            for status, value in grade_counts.items()
        },
    }


def aggregate_category_metrics(rows: list[dict], include_crag: bool = False) -> dict:
    category_summary = {}
    for category in sorted({row["category"] for row in rows}):
        category_rows = [row for row in rows if row["category"] == category]
        category_metrics = aggregate_metrics(category_rows)
        if include_crag:
            category_metrics.update(aggregate_crag_routes(category_rows))
        category_summary[category] = category_metrics
    return category_summary


async def evaluate_configuration(
    args: argparse.Namespace,
    config_name: str,
    profile: str,
    dataset: list[dict],
    mapping: dict,
    question_index: dict[str, dict],
    crag: bool = False,
    web_enabled: bool = False,
) -> dict:
    rows: list[dict] = []
    client = httpx.AsyncClient(base_url=args.api_base, timeout=args.timeout)
    try:
        for index, sample in enumerate(dataset, start=1):
            started = time.perf_counter()
            try:
                trace: dict[str, Any] | None = None
                if crag:
                    response, trace = await retrieve_crag(
                        client,
                        mapping,
                        args.token,
                        sample["query"],
                        profile,
                        args.top_k,
                        web_enabled,
                    )
                else:
                    response = await retrieve_profile(
                        client,
                        mapping,
                        args.token,
                        sample["query"],
                        profile,
                        args.top_k,
                    )
                latency_ms = (time.perf_counter() - started) * 1000
                mapped = map_results(response["results"], mapping, question_index)
                retrieved_ids = [item["canonical_id"] for item in mapped if item["canonical_id"]]
                metrics = evaluate_query(retrieved_ids, sample["relevance"], CUTOFFS)
                rows.append(
                    {
                        "query_id": sample["query_id"],
                        "category": sample["category"],
                        "query": sample["query"],
                        "status": "COMPLETED",
                        "latency_ms": round(latency_ms, 3),
                        "result_count": len(mapped),
                        "metrics": metrics,
                        "retrieved": mapped,
                        "crag": trace,
                    }
                )
            except Exception as error:
                rows.append(
                    {
                        "query_id": sample["query_id"],
                        "category": sample["category"],
                        "query": sample["query"],
                        "status": "FAILED",
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "result_count": 0,
                        "metrics": {},
                        "retrieved": [],
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
            print(f"[{config_name}] {index}/{len(dataset)} {sample['query_id']} {rows[-1]['status']}")
    finally:
        await client.aclose()
    summary = aggregate_metrics(rows)
    if crag:
        summary.update(aggregate_crag_routes(rows))
    category_summary = aggregate_category_metrics(rows, include_crag=crag)
    return {
        "name": config_name,
        "profile": profile,
        "crag_enabled": crag,
        "web_search_enabled": web_enabled,
        "summary": summary,
        "category_summary": category_summary,
        "queries": rows,
    }


def runtime_snapshot(args: argparse.Namespace, profiles: list[str]) -> dict:
    from app.api.v1.retrieval import FUSION_WEIGHTS
    from app.core.config import settings
    from app.services.crag_workflow import CRAG_PROMPT_VERSION
    from app.services.answer_critic import CRITIC_PROMPT_VERSION
    from app.services.interview_conductor import CONDUCTOR_PROMPT_VERSION
    from app.services.interview_evaluator import EVALUATION_PROMPT_VERSION
    from app.services.interview_planner import PROMPT_VERSION

    return {
        "models": {
            "llm": settings.LLM_MODEL,
            "llm_mini": settings.LLM_MINI_MODEL,
            "embedding": settings.EMBEDDING_MODEL_NAME,
            "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
            "reranker": settings.RERANK_MODEL_NAME,
        },
        "prompt_versions": {
            "planner": PROMPT_VERSION,
            "conductor": CONDUCTOR_PROMPT_VERSION,
            "evaluator": EVALUATION_PROMPT_VERSION,
            "crag": CRAG_PROMPT_VERSION,
            "answer_critic": CRITIC_PROMPT_VERSION,
        },
        "retrieval": {
            "profiles": profiles,
            "fusion_weights": dict(FUSION_WEIGHTS),
            "top_k": args.top_k,
            "crag_profile": args.crag_profile,
            "crag_max_rewrites": settings.CRAG_MAX_REWRITES,
            "crag_max_web_searches": settings.CRAG_MAX_WEB_SEARCHES,
        },
    }


def report_directory(run_id: str | None = None) -> Path:
    value = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_ROOT / value
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_reports(report_dir: Path, payload: dict) -> None:
    raw_path = report_dir / "results.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_rows = []
    for configuration in payload["configurations"]:
        summary_rows.append({"configuration": configuration["name"], **configuration["summary"]})
    columns = sorted({key for row in summary_rows for key in row})
    with (report_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(summary_rows)

    detail_rows = []
    for configuration in payload["configurations"]:
        for row in configuration["queries"]:
            detail_rows.append(
                {
                    "configuration": configuration["name"],
                    "query_id": row["query_id"],
                    "category": row["category"],
                    "status": row["status"],
                    "latency_ms": row["latency_ms"],
                    "result_count": row["result_count"],
                    **row.get("metrics", {}),
                    "error": row.get("error", ""),
                }
            )
    detail_columns = sorted({key for row in detail_rows for key in row})
    with (report_dir / "details.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=detail_columns)
        writer.writeheader()
        writer.writerows(detail_rows)

    category_rows = []
    for configuration in payload["configurations"]:
        for category, summary in configuration.get("category_summary", {}).items():
            category_rows.append(
                {
                    "configuration": configuration["name"],
                    "category": category,
                    **summary,
                }
            )
    if category_rows:
        category_columns = sorted({key for row in category_rows for key in row})
        with (report_dir / "categories.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=category_columns)
            writer.writeheader()
            writer.writerows(category_rows)

    preferred = [
        "configuration",
        "reciprocal_rank",
        "recall@5",
        "ndcg@5",
        "hit@5",
        "latency_mean_ms",
        "latency_p95_ms",
        "crag_rewrite_rate",
        "crag_web_search_rate",
        "failed_query_count",
    ]
    lines = [
        "# Retrieval Evaluation Report",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Dataset: `{payload['dataset_id']}` ({payload['query_count']} queries)",
        f"- Corpus: `{payload['corpus_id']}`",
        f"- Top K: `{payload['top_k']}`",
        "",
        "| " + " | ".join(preferred) + " |",
        "| " + " | ".join(["---"] * len(preferred)) + " |",
    ]
    for row in summary_rows:
        lines.append(
            "| " + " | ".join(str(row.get(column, "")) for column in preferred) + " |"
        )
    crag_rows = [
        row for row in summary_rows if int(row.get("crag_case_count", 0) or 0) > 0
    ]
    if crag_rows:
        crag_columns = [
            "configuration",
            "crag_rewrite_rate",
            "crag_web_search_rate",
            "crag_model_grader_call_rate",
            "crag_fallback_grader_call_rate",
            "crag_fallback_case_rate",
            "crag_grade_sufficient_rate",
            "crag_grade_partial_rate",
            "crag_grade_irrelevant_rate",
        ]
        lines.extend(
            [
                "",
                "## CRAG Routing",
                "",
                "| " + " | ".join(crag_columns) + " |",
                "| " + " | ".join(["---"] * len(crag_columns)) + " |",
            ]
        )
        for row in crag_rows:
            lines.append(
                "| "
                + " | ".join(str(row.get(column, "")) for column in crag_columns)
                + " |"
            )
    runtime = payload.get("runtime")
    if runtime:
        lines.extend(
            [
                "",
                "## Runtime Snapshot",
                "",
                "```json",
                json.dumps(runtime, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `reciprocal_rank` is MRR across all successful queries.",
            "- `recall@5` measures how many annotated relevant question blocks are retrieved.",
            "- `ndcg@5` rewards highly relevant blocks appearing earlier.",
            "- Compare quality together with latency; a higher score alone is not sufficient.",
            "- Web results are recorded in CRAG traces but excluded from local corpus relevance metrics.",
            "",
        ]
    )
    (report_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


async def run_evaluation(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    dataset = load_jsonl(DATASET_PATH)
    corpus_errors = [*verify_sources(manifest), *verify_fixtures(manifest)]
    if corpus_errors:
        raise ValueError("\n".join(corpus_errors))
    question_index = corpus_question_index(manifest)
    errors = validate_dataset(dataset, question_index)
    if errors:
        raise ValueError("\n".join(errors))
    mapping = load_mapping()
    mapping_errors = validate_mapping(mapping, manifest)
    if mapping_errors:
        raise ValueError("\n".join(mapping_errors))
    profiles = ALL_PROFILES if args.all_profiles else args.profiles
    configurations = []
    for profile in profiles:
        configurations.append(
            await evaluate_configuration(
                args, profile, profile, dataset, mapping, question_index
            )
        )
    if args.include_crag:
        configurations.append(
            await evaluate_configuration(
                args,
                "CRAG_LOCAL",
                args.crag_profile,
                dataset,
                mapping,
                question_index,
                crag=True,
            )
        )
    if args.include_crag_web:
        configurations.append(
            await evaluate_configuration(
                args,
                "CRAG_WEB",
                args.crag_profile,
                dataset,
                mapping,
                question_index,
                crag=True,
                web_enabled=True,
            )
        )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "retrieval-v1",
        "corpus_id": manifest["corpus_id"],
        "query_count": len(dataset),
        "top_k": args.top_k,
        "api_base": args.api_base,
        "runtime": runtime_snapshot(
            args, [configuration["name"] for configuration in configurations]
        ),
        "configurations": configurations,
    }
    output = report_directory(run_id)
    write_reports(output, payload)
    print(f"reports written to {output}")


def rebuild_report(input_path: Path, output_name: str | None) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    name = output_name or f"{payload['run_id']}-rebuilt"
    output = report_directory(name)
    write_reports(output, payload)
    print(f"reports rebuilt at {output}")


def write_critic_reports(report_dir: Path, payload: dict) -> None:
    (report_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = payload["summary"]
    with (report_dir / "summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)

    detail_rows = []
    for row in payload["cases"]:
        detail_rows.append(
            {
                "case_id": row["case_id"],
                "competency": row["competency"],
                **row["metrics"],
                "gold_score_range": json.dumps(row["gold"]["score_range"]),
                "predicted_score": row["prediction"]["score"],
                "gold_action": row["gold"]["next_action"],
                "predicted_action": row["prediction"]["next_action"],
                "gold_difficulty_delta": row["gold"]["difficulty_delta"],
                "predicted_difficulty_delta": row["prediction"]["difficulty_delta"],
                "gold_knowledge_gaps": json.dumps(
                    row["gold"].get("knowledge_gaps", []), ensure_ascii=False
                ),
                "predicted_knowledge_gaps": json.dumps(
                    row["prediction"].get("knowledge_gaps", []), ensure_ascii=False
                ),
            }
        )
    detail_columns = list(detail_rows[0]) if detail_rows else []
    with (report_dir / "details.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=detail_columns)
        writer.writeheader()
        writer.writerows(detail_rows)

    competency_rows = [
        {"competency": competency, **metrics}
        for competency, metrics in payload["competency_summary"].items()
    ]
    if competency_rows:
        with (report_dir / "competencies.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(competency_rows[0]))
            writer.writeheader()
            writer.writerows(competency_rows)

    metric_names = [
        "score_in_range",
        "action_accuracy",
        "difficulty_accuracy",
        "gap_precision",
        "gap_recall",
        "gap_f1",
        "gap_exact_match",
        "fallback_prediction_rate",
    ]
    lines = [
        "# Critic Regression Report",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Dataset: `{payload['dataset_id']}` ({payload['summary']['case_count']} cases)",
        f"- Predictions: `{payload['prediction_file']}`",
        f"- Models: `{', '.join(payload['prediction_metadata']['model_names']) or 'not recorded'}`",
        f"- Prompt versions: `{', '.join(payload['prediction_metadata']['prompt_versions']) or 'not recorded'}`",
        "",
        "| metric | value |",
        "| --- | ---: |",
        *[f"| {name} | {summary.get(name, '')} |" for name in metric_names],
        "",
        "## Interpretation",
        "",
        "- `score_in_range` checks whether the predicted score falls inside the annotated interval.",
        "- Action and difficulty accuracy evaluate the next interview decision.",
        "- Knowledge gaps use normalized exact labels and report precision, recall, F1, and exact match.",
        "",
    ]
    (report_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def score_critic(args: argparse.Namespace) -> None:
    dataset = load_jsonl(CRITIC_DATASET_PATH)
    predictions = load_jsonl(args.predictions)
    errors = [
        *validate_critic_dataset(dataset),
        *validate_critic_predictions(dataset, predictions),
    ]
    if errors:
        raise ValueError("\n".join(errors))

    run_id = f"critic-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    payload = build_critic_payload(dataset, predictions, args.predictions, run_id)
    output = report_directory(run_id)
    write_critic_reports(output, payload)
    print(f"critic reports written to {output}")


def build_critic_payload(
    dataset: list[dict],
    predictions: list[dict],
    prediction_path: Path,
    run_id: str,
) -> dict:

    prediction_by_id = {row["case_id"]: row for row in predictions}
    prediction_metadata = {
        "model_names": sorted(
            {
                str(row["model_name"])
                for row in predictions
                if row.get("model_name")
            }
        ),
        "prompt_versions": sorted(
            {
                str(row["prompt_version"])
                for row in predictions
                if row.get("prompt_version")
            }
        ),
    }
    rows = []
    for case in dataset:
        prediction = prediction_by_id[case["case_id"]]
        rows.append(
            {
                "case_id": case["case_id"],
                "competency": case["competency"],
                "gold": case["gold"],
                "prediction": prediction,
                "metrics": evaluate_critic_prediction(case, prediction),
            }
        )

    summary = aggregate_critic_metrics(rows)
    fallback_count = sum(
        1 for row in predictions if row.get("decision_source") == "FALLBACK_RULE"
    )
    summary.update(
        {
            "model_prediction_count": len(predictions) - fallback_count,
            "fallback_prediction_count": fallback_count,
            "fallback_prediction_rate": round(
                fallback_count / len(predictions), 6
            ) if predictions else 0.0,
        }
    )
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "interview-turn-v1",
        "prediction_file": str(prediction_path.resolve()),
        "prediction_metadata": prediction_metadata,
        "summary": summary,
        "competency_summary": {
            competency: aggregate_critic_metrics(
                [row for row in rows if row["competency"] == competency]
            )
            for competency in sorted({row["competency"] for row in rows})
        },
        "cases": rows,
    }
    return payload


async def run_critic_evaluation() -> None:
    from app.core.config import settings
    from app.services.answer_critic import (
        CRITIC_PROMPT_VERSION,
        fallback_critique_values,
        generate_critique,
    )

    dataset = load_jsonl(CRITIC_DATASET_PATH)
    errors = validate_critic_dataset(dataset)
    if errors:
        raise ValueError("\n".join(errors))
    predictions = []
    for index, case in enumerate(dataset, start=1):
        decision_source = "MODEL"
        error_message = None
        try:
            generated = await generate_critique(
                {
                    "interview_mode": "MOCK",
                    "question": {
                        "content": case["question"],
                        "competency": case["competency"],
                        "difficulty": "MEDIUM",
                        "expected_points": [],
                    },
                    "answer": case["answer"],
                    "reference_evidence": [],
                }
            )
        except Exception as error:
            decision_source = "FALLBACK_RULE"
            error_message = f"{type(error).__name__}: {error}"[:2000]
            generated = fallback_critique_values(case["answer"], "MEDIUM", [])
        predictions.append(
            {
                "case_id": case["case_id"],
                "score": generated.score,
                "next_action": generated.next_action,
                "difficulty_delta": generated.difficulty_delta,
                "knowledge_gaps": generated.knowledge_gaps,
                "strengths": generated.strengths,
                "answer_evidence": generated.answer_evidence,
                "reason": generated.reason,
                "confidence": generated.confidence,
                "decision_source": decision_source,
                "error_message": error_message,
                "model_name": (
                    settings.LLM_MINI_MODEL if decision_source == "MODEL" else None
                ),
                "prompt_version": CRITIC_PROMPT_VERSION,
            }
        )
        print(f"[CRITIC] {index}/{len(dataset)} {case['case_id']} {decision_source}")

    validation_errors = validate_critic_predictions(dataset, predictions)
    if validation_errors:
        raise ValueError("\n".join(validation_errors))
    run_id = f"critic-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output = report_directory(run_id)
    prediction_path = output / "predictions.jsonl"
    prediction_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in predictions) + "\n",
        encoding="utf-8",
    )
    payload = build_critic_payload(dataset, predictions, prediction_path, run_id)
    write_critic_reports(output, payload)
    print(f"critic evaluation written to {output}")


def verify_command() -> None:
    manifest = load_manifest()
    corpus_errors = [*verify_sources(manifest), *verify_fixtures(manifest)]
    if corpus_errors:
        raise ValueError("\n".join(corpus_errors))
    question_index = corpus_question_index(manifest)
    dataset = load_jsonl(DATASET_PATH)
    critic_dataset = load_jsonl(CRITIC_DATASET_PATH)
    errors = [
        *validate_dataset(dataset, question_index),
        *validate_critic_dataset(critic_dataset),
    ]
    if errors:
        raise ValueError("\n".join(errors))
    categories = defaultdict(int)
    for row in dataset:
        categories[row["category"]] += 1
    print(
        json.dumps(
            {
                "corpus_sources": len(manifest["sources"]),
                "corpus_questions": len(question_index),
                "evaluation_queries": len(dataset),
                "critic_cases": len(critic_dataset),
                "categories": categories,
                "status": "VALID",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="InterviewPilot offline evaluation")
    subparsers = root.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify", help="Verify frozen corpus and annotations")

    report = subparsers.add_parser("report", help="Rebuild CSV and Markdown reports")
    report.add_argument("--input", required=True, type=Path)
    report.add_argument("--output-name")

    critic = subparsers.add_parser(
        "score-critic", help="Score Critic predictions against interview-turn-v1"
    )
    critic.add_argument("--predictions", required=True, type=Path)
    subparsers.add_parser(
        "run-critic", help="Generate and score predictions with the production Answer Critic"
    )

    prepare = subparsers.add_parser("prepare", help="Create and ingest evaluation corpus")
    prepare.add_argument("--workspace-id", required=True)
    prepare.add_argument("--token", default=os.getenv("EVAL_ACCESS_TOKEN"), required=False)
    prepare.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    prepare.add_argument("--knowledge-base-name", default="Evaluation Corpus v1")
    prepare.add_argument(
        "--purpose",
        choices=["PERSONAL_LEARNING", "TECHNICAL_STANDARD"],
        default="PERSONAL_LEARNING",
    )
    prepare.add_argument("--visibility", choices=["PRIVATE", "WORKSPACE"], default="PRIVATE")
    prepare.add_argument("--timeout", type=float, default=180.0)
    prepare.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True)
    prepare.add_argument("--wait-timeout", type=float, default=1800.0)
    prepare.add_argument("--poll-interval", type=float, default=5.0)

    run = subparsers.add_parser("run", help="Run retrieval and CRAG evaluation")
    run.add_argument("--token", default=os.getenv("EVAL_ACCESS_TOKEN"), required=False)
    run.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    run.add_argument("--top-k", type=int, default=10)
    run.add_argument("--timeout", type=float, default=180.0)
    run.add_argument("--profiles", nargs="+", choices=ALL_PROFILES, default=DEFAULT_PROFILES)
    run.add_argument("--all-profiles", action="store_true")
    run.add_argument("--include-crag", action="store_true")
    run.add_argument("--include-crag-web", action="store_true")
    run.add_argument(
        "--crag-profile",
        choices=ALL_PROFILES,
        default="VECTOR_TRIGRAM_BM25_RERANK",
    )
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command in {"prepare", "run"} and not args.token:
        raise SystemExit("Provide --token or set EVAL_ACCESS_TOKEN")
    if args.command == "verify":
        verify_command()
    elif args.command == "prepare":
        asyncio.run(prepare_corpus(args))
    elif args.command == "run":
        asyncio.run(run_evaluation(args))
    elif args.command == "report":
        rebuild_report(args.input, args.output_name)
    elif args.command == "score-critic":
        score_critic(args)
    elif args.command == "run-critic":
        asyncio.run(run_critic_evaluation())


if __name__ == "__main__":
    main()
