from __future__ import annotations

import unittest

from app.services.answer_critic import GeneratedCritique, fallback_critique_values
from app.services.interview_gap_policy import filter_technical_gaps
from app.services.interview_plan_reviser import shift_difficulty


class AnswerCriticContractTest(unittest.TestCase):
    def test_model_output_variants_are_normalized(self) -> None:
        critique = GeneratedCritique.model_validate(
            {
                "score": "8.5/10",
                "strengths": "说明了状态边界",
                "knowledge_gaps": None,
                "answer_evidence": "节点只更新负责字段",
                "next_action": "raise difficulty",
                "difficulty_delta": "increase",
                "confidence": "high",
                "reason": "回答完整，可以提高难度",
            }
        )

        self.assertEqual(critique.score, 85)
        self.assertEqual(critique.strengths, ["说明了状态边界"])
        self.assertEqual(critique.next_action, "INCREASE_DIFFICULTY")
        self.assertEqual(critique.difficulty_delta, 1)
        self.assertEqual(critique.confidence, 0.8)

    def test_fallback_is_explicitly_conservative(self) -> None:
        critique = fallback_critique_values("回答很短", "MEDIUM", ["事务边界"])

        self.assertEqual(critique.score, 25)
        self.assertEqual(critique.next_action, "DECREASE_DIFFICULTY")
        self.assertEqual(critique.knowledge_gaps, ["事务边界"])

    def test_difficulty_shift_stays_within_bounds(self) -> None:
        self.assertEqual(shift_difficulty("EASY", -1), "EASY")
        self.assertEqual(shift_difficulty("MEDIUM", 1), "HARD")
        self.assertEqual(shift_difficulty("HARD", 1), "HARD")

    def test_non_technical_feedback_is_not_a_knowledge_gap(self) -> None:
        gaps = filter_technical_gaps(
            [
                "术语使用‘判卷’而非‘判级’，可能表述不准确",
                "向量检索中的多租户隔离策略",
            ]
        )

        self.assertEqual(gaps, ["向量检索中的多租户隔离策略"])


if __name__ == "__main__":
    unittest.main()
