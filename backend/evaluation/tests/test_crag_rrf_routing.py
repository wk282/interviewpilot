from __future__ import annotations

import unittest

from app.services.crag_workflow import CRAGWorkflow


def workflow(profile: str = "VECTOR_BM25_RRF") -> CRAGWorkflow:
    return CRAGWorkflow(
        None,
        None,
        None,
        None,
        None,
        retrieval_profile=profile,
        web_enabled_override=False,
    )


class CragRrfRoutingTest(unittest.TestCase):
    def test_rrf_fast_path_requires_absolute_and_cross_channel_signals(self) -> None:
        evidence = [
            {
                "fusion_score": 0.032787,
                "vector_similarity": 0.82,
                "vector_rank": 1,
                "bm25_rank": 2,
                "retrieval_sources": ["VECTOR", "BM25"],
            },
            {
                "fusion_score": 0.031754,
                "vector_similarity": 0.76,
                "vector_rank": 3,
                "bm25_rank": 4,
                "retrieval_sources": ["VECTOR", "BM25"],
            },
        ]

        result = workflow().local_fast_path_grade(evidence)

        self.assertIsNotNone(result)
        assert result is not None
        grade, strategy, signals = result
        self.assertEqual(grade.status, "sufficient")
        self.assertEqual(strategy, "rrf_cross_channel_agreement")
        self.assertEqual(signals["vector_rank"], 1)
        self.assertEqual(signals["bm25_rank"], 2)

    def test_high_raw_rrf_score_alone_does_not_enter_fast_path(self) -> None:
        evidence = [
            {
                "fusion_score": 0.032787,
                "vector_similarity": 0.35,
                "vector_rank": 1,
                "bm25_rank": None,
                "retrieval_sources": ["VECTOR"],
            },
            {
                "fusion_score": 0.031754,
                "vector_similarity": 0.30,
                "vector_rank": 2,
                "bm25_rank": None,
                "retrieval_sources": ["VECTOR"],
            },
        ]

        self.assertIsNone(workflow().local_fast_path_grade(evidence))

    def test_rrf_grader_failure_does_not_compare_raw_score_with_point_five(self) -> None:
        grade = workflow().fallback_grade(
            [{"fusion_score": 0.032787}, {"fusion_score": 0.031754}]
        )

        self.assertEqual(grade.status, "partial")
        self.assertEqual(grade.recommended_action, "generate")
        self.assertEqual(grade.confidence, 0.5)

    def test_recommended_generate_wins_over_partial_status(self) -> None:
        state = {
            "grade": {
                "status": "partial",
                "recommended_action": "generate",
            },
            "rewrite_count": 0,
            "web_search_count": 0,
        }

        self.assertEqual(workflow().route_after_grade(state), "generate")

    def test_non_rrf_profile_keeps_normalized_score_fast_path(self) -> None:
        evidence = [{"fusion_score": 0.8}, {"fusion_score": 0.7}]

        result = workflow("VECTOR_BM25").local_fast_path_grade(evidence)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[1], "normalized_fusion_score")


if __name__ == "__main__":
    unittest.main()
