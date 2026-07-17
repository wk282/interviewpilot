from __future__ import annotations

import unittest

from evaluation.metrics.retrieval import aggregate_metrics, evaluate_query


class RetrievalMetricsTest(unittest.TestCase):
    def test_rank_metrics_reward_relevant_results(self) -> None:
        metrics = evaluate_query(
            ["irrelevant", "q1", "q2"],
            {"q1": 3, "q2": 1},
            (1, 3),
        )

        self.assertEqual(metrics["reciprocal_rank"], 0.5)
        self.assertEqual(metrics["hit@1"], 0.0)
        self.assertEqual(metrics["hit@3"], 1.0)
        self.assertEqual(metrics["recall@3"], 1.0)
        self.assertGreater(metrics["ndcg@3"], 0.0)

    def test_duplicate_canonical_ids_are_counted_once(self) -> None:
        metrics = evaluate_query(["q1", "q1"], {"q1": 3}, (1, 3))

        self.assertEqual(metrics["recall@3"], 1.0)
        self.assertEqual(metrics["ndcg@3"], 1.0)

    def test_aggregate_includes_failures_and_latency(self) -> None:
        rows = [
            {
                "status": "COMPLETED",
                "metrics": {"reciprocal_rank": 1.0},
                "latency_ms": 10,
                "result_count": 3,
            },
            {"status": "FAILED", "metrics": {}, "latency_ms": 20, "result_count": 0},
        ]

        summary = aggregate_metrics(rows)

        self.assertEqual(summary["successful_query_count"], 1)
        self.assertEqual(summary["failed_query_count"], 1)
        self.assertEqual(summary["latency_mean_ms"], 10.0)


if __name__ == "__main__":
    unittest.main()
