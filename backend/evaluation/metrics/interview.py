from __future__ import annotations


def _normalize_labels(values: list[str] | None) -> set[str]:
    return {value.strip().lower() for value in values or [] if value.strip()}


def evaluate_critic_prediction(case: dict, prediction: dict) -> dict[str, float]:
    gold = case["gold"]
    score = float(prediction.get("score", -1))
    minimum, maximum = gold["score_range"]
    expected_gaps = _normalize_labels(gold.get("knowledge_gaps"))
    predicted_gaps = _normalize_labels(prediction.get("knowledge_gaps"))
    gap_hits = len(expected_gaps & predicted_gaps)
    gap_precision = gap_hits / len(predicted_gaps) if predicted_gaps else (
        1.0 if not expected_gaps else 0.0
    )
    gap_recall = gap_hits / len(expected_gaps) if expected_gaps else (
        1.0 if not predicted_gaps else 0.0
    )
    return {
        "score_in_range": 1.0 if minimum <= score <= maximum else 0.0,
        "action_accuracy": 1.0
        if prediction.get("next_action") == gold["next_action"]
        else 0.0,
        "difficulty_accuracy": 1.0
        if prediction.get("difficulty_delta") == gold["difficulty_delta"]
        else 0.0,
        "gap_recall": gap_recall,
        "gap_precision": gap_precision,
        "gap_f1": (
            2 * gap_precision * gap_recall / (gap_precision + gap_recall)
            if gap_precision + gap_recall
            else 0.0
        ),
        "gap_exact_match": 1.0 if expected_gaps == predicted_gaps else 0.0,
    }


def aggregate_critic_metrics(rows: list[dict]) -> dict[str, float | int]:
    if not rows:
        return {"case_count": 0}
    names = list(rows[0]["metrics"])
    return {
        "case_count": len(rows),
        **{
            name: round(sum(row["metrics"][name] for row in rows) / len(rows), 6)
            for name in names
        },
    }
