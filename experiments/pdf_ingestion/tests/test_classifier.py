from __future__ import annotations

import unittest

from experiments.pdf_ingestion.pdf_lab.classifier import classify_page
from experiments.pdf_ingestion.pdf_lab.contracts import PageKind, PageObservation


class PageClassifierTest(unittest.TestCase):
    def test_native_text_page_does_not_require_ocr(self) -> None:
        observation = PageObservation(500, 8, 0.05, 1.0)

        self.assertEqual(classify_page(observation), PageKind.TEXT)

    def test_full_page_image_without_text_requires_ocr(self) -> None:
        observation = PageObservation(0, 0, 0.98, 1.0)

        self.assertEqual(classify_page(observation), PageKind.SCANNED)

    def test_text_and_large_image_are_classified_as_mixed(self) -> None:
        observation = PageObservation(90, 3, 0.55, 1.0)

        self.assertEqual(classify_page(observation), PageKind.MIXED)

    def test_garbled_native_text_is_not_trusted(self) -> None:
        observation = PageObservation(300, 5, 0.0, 0.40)

        self.assertEqual(classify_page(observation), PageKind.SCANNED)


if __name__ == "__main__":
    unittest.main()
