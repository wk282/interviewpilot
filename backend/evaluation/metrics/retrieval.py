from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable


def _gain(relevance: int) -> float:
    return float((2**relevance) - 1)


def _dcg(relevances: Iterable[int]) -> float:
    return sum(
        _gain(relevance) / math.log2(rank + 1)
        for rank, relevance in enumerate(relevances, start=1)
    )


def evaluate_query(
    retrieved_ids: list[str],
    relevance_by_id: dict[str, int],
    cutoffs: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, float]:
    retrieved_ids = list(dict.fromkeys(retrieved_ids))
    relevant_ids = {item_id for item_id, grade in relevance_by_id.items() if grade > 0}
    metrics: dict[str, float] = {}

    first_relevant_rank = next(
        (rank for rank, item_id in enumerate(retrieved_ids, start=1) if item_id in relevant_ids),
        None,
    )
    metrics["reciprocal_rank"] = (
        1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
    )

    for cutoff in cutoffs:
        top_ids = retrieved_ids[:cutoff]
        hit_count = len(set(top_ids) & relevant_ids)
        metrics[f"hit@{cutoff}"] = 1.0 if hit_count else 0.0
        metrics[f"recall@{cutoff}"] = (
            hit_count / len(relevant_ids) if relevant_ids else 0.0
        )
        observed = [relevance_by_id.get(item_id, 0) for item_id in top_ids]
        ideal = sorted(relevance_by_id.values(), reverse=True)[:cutoff]
        ideal_dcg = _dcg(ideal)
        metrics[f"ndcg@{cutoff}"] = _dcg(observed) / ideal_dcg if ideal_dcg else 0.0
    return metrics


def aggregate_metrics(rows: list[dict]) -> dict:
    successful = [row for row in rows if row.get("status") == "COMPLETED"]
    failures = [row for row in rows if row.get("status") != "COMPLETED"]
    if not successful:
        return {
            "query_count": len(rows),
            "successful_query_count": 0,
            "failed_query_count": len(failures),
        }

    totals: dict[str, float] = defaultdict(float)
    for row in successful:
        for name, value in row["metrics"].items():
            totals[name] += float(value)
    count = len(successful)
    summary = {
        "query_count": len(rows),
        "successful_query_count": count,
        "failed_query_count": len(failures),
        **{name: round(total / count, 6) for name, total in totals.items()},
    }
    latencies = sorted(float(row["latency_ms"]) for row in successful)
    summary["latency_mean_ms"] = round(sum(latencies) / count, 3)
    summary["latency_p95_ms"] = round(
        latencies[max(0, math.ceil(count * 0.95) - 1)], 3
    )
    summary["mean_result_count"] = round(
        sum(int(row["result_count"]) for row in successful) / count, 3
    )
    return summary
