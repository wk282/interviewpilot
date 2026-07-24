from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace

from app.services.interview_conductor import build_retrieval_query, fallback_question
from app.services.interview_plan_reviser import AdaptiveGuidance


class InterviewConductorRetrievalQueryTest(unittest.TestCase):
    def test_query_contains_only_retrieval_intent_fields(self) -> None:
        query = build_retrieval_query(
            position_title="AI application engineer",
            position_description="Build production RAG systems",
            latest_question="How do you evaluate retrieval quality?",
            target_competency="retrieval evaluation",
            knowledge_gaps=["NDCG", "MRR"],
        )

        self.assertEqual(
            query.splitlines(),
            [
                "AI application engineer",
                "Build production RAG systems",
                "How do you evaluate retrieval quality?",
                "retrieval evaluation",
                "NDCG",
                "MRR",
            ],
        )

    def test_non_technical_feedback_is_excluded_from_query(self) -> None:
        query = build_retrieval_query(
            position_title="AI application engineer",
            position_description=None,
            latest_question=None,
            knowledge_gaps=[
                "术语使用‘判卷’而非‘判级’，可能表述不准确",
                "BM25与向量召回的融合权衡",
            ],
        )

        self.assertNotIn("判卷", query)
        self.assertIn("BM25与向量召回的融合权衡", query)

    def test_fallback_question_uses_competency_instead_of_raw_gap(self) -> None:
        guidance = AdaptiveGuidance(
            critique_id=uuid.uuid4(),
            plan_revision_id=uuid.uuid4(),
            plan_version=1,
            action="FOLLOW_UP",
            target_competency="混合检索",
            target_difficulty="MEDIUM",
            knowledge_gaps=["术语使用‘判卷’而非‘判级’，可能表述不准确"],
            rationale="continue",
            score=60,
            remaining_question_budget=3,
            competency_budget={"混合检索": 1},
        )

        turn = fallback_question(
            SimpleNamespace(title="AI application engineer"),
            SimpleNamespace(sections=[]),
            set(),
            1,
            guidance,
        )

        self.assertNotIn("判卷", turn.content or "")
        self.assertIn("混合检索", turn.content or "")


if __name__ == "__main__":
    unittest.main()
