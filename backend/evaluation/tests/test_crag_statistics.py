from __future__ import annotations

import unittest

from app.services.crag_workflow import RetrievalGrade
from evaluation.runner import aggregate_category_metrics, aggregate_crag_routes


class CragStatisticsTest(unittest.TestCase):
    def test_retrieval_grade_accepts_single_missing_aspect(self) -> None:
        grade = RetrievalGrade.model_validate(
            {
                "status": "partial",
                "confidence": 0.7,
                "missing_aspects": "缺少多租户隔离细节",
                "recommended_action": "web_search",
            }
        )

        self.assertEqual(grade.missing_aspects, ["缺少多租户隔离细节"])

    def test_retrieval_grade_normalizes_qualitative_confidence(self) -> None:
        grade = RetrievalGrade.model_validate(
            {
                "status": "partial",
                "confidence": "moderate",
                "missing_aspects": [],
                "recommended_action": "web_search",
            }
        )

        self.assertEqual(grade.confidence, 0.6)

    def test_routes_are_derived_from_trace_nodes(self) -> None:
        rows = [
            {
                "status": "COMPLETED",
                "crag": {
                    "grade": {"status": "sufficient"},
                    "trace": [
                        {"node": "retrieve"},
                        {"node": "retrieval_grader", "grading_source": "model"},
                    ],
                },
            },
            {
                "status": "COMPLETED",
                "crag": {
                    "grade": {"status": "partial"},
                    "trace": [
                        {"node": "retrieve"},
                        {"node": "rewrite_query"},
                        {"node": "web_search"},
                        {"node": "retrieval_grader", "grading_source": "fallback_rule"},
                    ],
                },
            },
        ]

        summary = aggregate_crag_routes(rows)

        self.assertEqual(summary["crag_case_count"], 2)
        self.assertEqual(summary["crag_rewrite_rate"], 0.5)
        self.assertEqual(summary["crag_web_search_rate"], 0.5)
        self.assertEqual(summary["crag_grade_sufficient_rate"], 0.5)
        self.assertEqual(summary["crag_grader_call_count"], 2)
        self.assertEqual(summary["crag_model_grader_call_rate"], 0.5)
        self.assertEqual(summary["crag_fallback_grader_call_rate"], 0.5)
        self.assertEqual(summary["crag_fallback_case_rate"], 0.5)

    def test_category_summary_is_available_without_crag(self) -> None:
        rows = [
            {
                "category": "rag",
                "status": "COMPLETED",
                "metrics": {"reciprocal_rank": 1.0},
                "latency_ms": 12,
                "result_count": 4,
            }
        ]

        summary = aggregate_category_metrics(rows)

        self.assertEqual(summary["rag"]["successful_query_count"], 1)
        self.assertEqual(summary["rag"]["reciprocal_rank"], 1.0)


if __name__ == "__main__":
    unittest.main()
