from __future__ import annotations

import unittest
import uuid

from app.api.v1.retrieval import reciprocal_rank_fusion


class ReciprocalRankFusionTest(unittest.TestCase):
    def test_absent_channel_does_not_contribute_to_score(self) -> None:
        first = uuid.uuid4()
        second = uuid.uuid4()
        scores = reciprocal_rank_fusion(
            [first, second],
            {
                "VECTOR": {first: 1, second: 2},
                "BM25": {first: 3},
            },
        )

        self.assertAlmostEqual(scores[first], 1 / 61 + 1 / 63)
        self.assertAlmostEqual(scores[second], 1 / 62)

    def test_cross_channel_top_result_receives_the_highest_score(self) -> None:
        first = uuid.uuid4()
        second = uuid.uuid4()
        scores = reciprocal_rank_fusion(
            [first, second],
            {
                "VECTOR": {first: 1, second: 2},
                "BM25": {first: 1, second: 4},
            },
        )

        self.assertGreater(scores[first], scores[second])


if __name__ == "__main__":
    unittest.main()
