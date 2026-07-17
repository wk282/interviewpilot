from __future__ import annotations

import unittest

from evaluation.runner import aggregate_crag_routes


class CragStatisticsTest(unittest.TestCase):
    def test_routes_are_derived_from_trace_nodes(self) -> None:
        rows = [
            {
                "status": "COMPLETED",
                "crag": {
                    "grade": {"status": "sufficient"},
                    "trace": [{"node": "retrieve"}, {"node": "retrieval_grader"}],
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
                    ],
                },
            },
        ]

        summary = aggregate_crag_routes(rows)

        self.assertEqual(summary["crag_case_count"], 2)
        self.assertEqual(summary["crag_rewrite_rate"], 0.5)
        self.assertEqual(summary["crag_web_search_rate"], 0.5)
        self.assertEqual(summary["crag_grade_sufficient_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
