from __future__ import annotations

import unittest

from evaluation.metrics.interview import (
    aggregate_critic_metrics,
    evaluate_critic_prediction,
)


class InterviewMetricsTest(unittest.TestCase):
    def test_exact_prediction_receives_full_credit(self) -> None:
        case = {
            "gold": {
                "score_range": [80, 95],
                "next_action": "INCREASE_DIFFICULTY",
                "difficulty_delta": 1,
                "knowledge_gaps": [],
            }
        }
        prediction = {
            "score": 90,
            "next_action": "INCREASE_DIFFICULTY",
            "difficulty_delta": 1,
            "knowledge_gaps": [],
        }

        metrics = evaluate_critic_prediction(case, prediction)

        self.assertTrue(all(value == 1.0 for value in metrics.values()))

    def test_gap_metrics_penalize_extra_labels(self) -> None:
        case = {
            "gold": {
                "score_range": [30, 50],
                "next_action": "FOLLOW_UP",
                "difficulty_delta": -1,
                "knowledge_gaps": ["state", "checkpoint"],
            }
        }
        prediction = {
            "score": 40,
            "next_action": "FOLLOW_UP",
            "difficulty_delta": -1,
            "knowledge_gaps": ["state", "unrelated"],
        }

        metrics = evaluate_critic_prediction(case, prediction)

        self.assertEqual(metrics["gap_precision"], 0.5)
        self.assertEqual(metrics["gap_recall"], 0.5)
        self.assertEqual(metrics["gap_exact_match"], 0.0)

    def test_aggregate_averages_cases(self) -> None:
        rows = [
            {"metrics": {"action_accuracy": 1.0}},
            {"metrics": {"action_accuracy": 0.0}},
        ]

        self.assertEqual(aggregate_critic_metrics(rows)["action_accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
