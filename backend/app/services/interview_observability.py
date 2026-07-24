import math
import uuid
from collections import Counter, defaultdict
from typing import Any

from app.db.models.interview import InterviewQuestion


STAGE_NAMES = {
    "TOTAL",
    "CRITIC",
    "PLAN_REVISER",
    "EMBEDDING",
    "KNOWLEDGE_RETRIEVAL",
    "RERANKER",
    "RETRIEVAL_GRADER",
    "QUERY_REWRITE",
    "WEB_SEARCH",
    "CRAG",
    "CONDUCTOR",
    "AI_QUEUE",
}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def numeric(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    return None


def percentile(values: list[float], ratio: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return round(ordered[index])


def latency_summary(values: list[float]) -> dict[str, int]:
    return {
        "sample_count": len(values),
        "average_latency_ms": round(sum(values) / len(values)),
        "p50_latency_ms": percentile(values, 0.5),
        "p95_latency_ms": percentile(values, 0.95),
        "max_latency_ms": round(max(values)),
    }


def usage_tokens(value: object) -> int:
    usage = as_dict(value)
    total = usage.get("total_tokens")
    return int(total) if isinstance(total, int) and total >= 0 else 0


def build_interview_observability(
    interview_id: uuid.UUID,
    questions: list[InterviewQuestion],
) -> dict:
    stage_values: dict[str, list[float]] = defaultdict(list)
    route_counts: Counter[str] = Counter()
    total_tokens = 0
    fallback_event_count = 0
    fallback_turn_count = 0
    measured_turn_count = 0

    def add_latency(stage: str, value: object) -> None:
        latency = numeric(value)
        if latency is not None and stage in STAGE_NAMES:
            stage_values[stage].append(latency)

    def add_concurrency(value: object) -> None:
        concurrency = as_dict(value)
        queue_wait_ms = numeric(concurrency.get("queue_wait_ms"))
        if queue_wait_ms is None:
            return
        add_latency("AI_QUEUE", queue_wait_ms)
        if queue_wait_ms >= 10:
            route_counts["ai_queue_wait"] += 1

    for question in questions:
        metadata = as_dict(question.decision_metadata)
        observability = as_dict(metadata.get("observability"))
        if not observability:
            continue
        measured_turn_count += 1
        turn_has_fallback = False
        add_latency(
            "TOTAL",
            observability.get("activation_total_latency_ms")
            or observability.get("total_latency_ms"),
        )

        crag = as_dict(observability.get("crag"))
        add_latency("CRAG", crag.get("latency_ms"))
        add_latency("EMBEDDING", crag.get("embedding_latency_ms"))
        add_latency(
            "KNOWLEDGE_RETRIEVAL",
            crag.get("knowledge_base_retrieval_latency_ms"),
        )
        add_latency("RERANKER", crag.get("reranker_latency_ms"))
        grade_status = crag.get("grade")
        if isinstance(grade_status, str):
            route_counts[f"grade_{grade_status}"] += 1

        conductor = as_dict(observability.get("conductor"))
        add_latency("CONDUCTOR", conductor.get("latency_ms"))
        add_concurrency(conductor.get("concurrency"))
        total_tokens += usage_tokens(conductor.get("usage"))
        if conductor.get("source") not in {None, "model"}:
            fallback_event_count += 1
            turn_has_fallback = True

        agent_graph = as_dict(observability.get("agent_graph"))
        agent_trace = agent_graph.get("trace")
        if agent_graph.get("checkpointed") is True:
            route_counts["checkpointed_turn"] += 1
        if agent_graph.get("pause_reason") == "WAIT_FOR_ANSWER":
            route_counts["paused_for_answer"] += 1
        if not isinstance(agent_trace, list):
            agent_trace = observability.get("feedback_trace")
        if isinstance(agent_trace, list):
            for raw_node in agent_trace:
                node = as_dict(raw_node)
                node_name = node.get("node")
                if node_name in {"answer_critic", "answer_critic_agent"}:
                    add_latency("CRITIC", node.get("latency_ms"))
                    critic_observability = as_dict(node.get("observability"))
                    add_concurrency(critic_observability.get("concurrency"))
                    total_tokens += usage_tokens(critic_observability.get("usage"))
                    if node.get("decision_source") == "FALLBACK_RULE":
                        fallback_event_count += 1
                        turn_has_fallback = True
                elif node_name in {"plan_reviser", "plan_reviser_agent"}:
                    add_latency("PLAN_REVISER", node.get("latency_ms"))
                    action = node.get("action")
                    if isinstance(action, str):
                        route_counts[f"reviser_{action.lower()}"] += 1
                elif node_name == "wait_for_answer":
                    route_counts["checkpoint_resume"] += 1

        retrieval_trace = metadata.get("retrieval_trace")
        if isinstance(retrieval_trace, list):
            for raw_node in retrieval_trace:
                node = as_dict(raw_node)
                node_name = node.get("node")
                if node_name == "retrieve":
                    retrieve_observability = as_dict(node.get("observability"))
                    reranker_observability = as_dict(
                        retrieve_observability.get("reranker")
                    )
                    add_concurrency(reranker_observability.get("concurrency"))
                elif node_name == "retrieval_grader":
                    add_latency("RETRIEVAL_GRADER", node.get("latency_ms"))
                    add_concurrency(node.get("concurrency"))
                    total_tokens += usage_tokens(node.get("usage"))
                    route_counts[f"grader_{node.get('grading_source', 'unknown')}"] += 1
                    if node.get("grading_source") == "fallback_rule":
                        fallback_event_count += 1
                        turn_has_fallback = True
                elif node_name == "rewrite_query":
                    add_latency("QUERY_REWRITE", node.get("latency_ms"))
                    add_concurrency(node.get("concurrency"))
                    total_tokens += usage_tokens(node.get("usage"))
                    route_counts["query_rewrite"] += 1
                    if node.get("rewrite_source") == "fallback_rule":
                        fallback_event_count += 1
                        turn_has_fallback = True
                elif node_name == "web_search":
                    add_latency("WEB_SEARCH", node.get("latency_ms"))
                    route_counts["web_search"] += 1
                    if node.get("error"):
                        fallback_event_count += 1
                        turn_has_fallback = True
        if turn_has_fallback:
            fallback_turn_count += 1

    stage_metrics = {
        stage: latency_summary(values)
        for stage, values in stage_values.items()
        if values
    }
    bottleneck_candidates = {
        stage: metrics["average_latency_ms"]
        for stage, metrics in stage_metrics.items()
        if stage not in {"TOTAL", "CRAG"}
    }
    bottleneck_stage = (
        max(bottleneck_candidates, key=bottleneck_candidates.get)
        if bottleneck_candidates
        else None
    )
    return {
        "interview_id": interview_id,
        "question_count": len(questions),
        "measured_turn_count": measured_turn_count,
        "total_tokens": total_tokens,
        "fallback_event_count": fallback_event_count,
        "fallback_turn_count": fallback_turn_count,
        "fallback_turn_rate": round(
            fallback_turn_count / measured_turn_count, 4
        ) if measured_turn_count else 0.0,
        "bottleneck_stage": bottleneck_stage,
        "stage_metrics": stage_metrics,
        "route_counts": dict(route_counts),
    }
