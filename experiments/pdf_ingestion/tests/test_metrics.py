from __future__ import annotations

import unittest

from experiments.pdf_ingestion.pdf_lab.metrics import (
    character_error_rate,
    route_accuracy,
)


class PdfEvaluationMetricsTest(unittest.TestCase):
    def test_character_error_rate_ignores_whitespace(self) -> None:
        self.assertEqual(character_error_rate("向量 检索", "向量\n检索"), 0.0)

    def test_character_error_rate_detects_ocr_substitution(self) -> None:
        self.assertGreater(character_error_rate("BM25检索", "BM2S检索"), 0.0)

    def test_route_accuracy(self) -> None:
        accuracy = route_accuracy(
            ["TEXT", "SCANNED", "MIXED"],
            ["TEXT", "SCANNED", "TEXT"],
        )

        self.assertAlmostEqual(accuracy, 2 / 3)


if __name__ == "__main__":
    unittest.main()
