from __future__ import annotations

import unittest

from experiments.pdf_ingestion.pdf_lab.contracts import (
    PageKind,
    PageObservation,
    ParsedDocument,
    ParsedPage,
    TextBlock,
)
from experiments.pdf_ingestion.pdf_lab.quality import build_quality_report


def make_document(text: str, *, confidence: float = 0.98) -> ParsedDocument:
    block = TextBlock(
        block_type="paragraph",
        text=text,
        source="OCR",
        confidence=confidence,
    )
    page = ParsedPage(
        page_number=1,
        kind=PageKind.SCANNED,
        blocks=[block],
        plain_text=text,
        observation=PageObservation(0, 0, 1.0, 1.0),
        used_ocr=True,
    )
    return ParsedDocument("sample.pdf", "TEST", "1", [page])


class PdfQualityReportTest(unittest.TestCase):
    def test_good_ocr_document_passes(self) -> None:
        document = make_document(
            "A sufficiently long OCR result describing vector retrieval and evaluation metrics."
        )

        report = build_quality_report(document)

        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["ocr_page_count"], 1)

    def test_low_confidence_ocr_is_blocked_before_chunking(self) -> None:
        document = make_document(
            "A sufficiently long OCR result that must not enter the vector pipeline.",
            confidence=0.42,
        )

        report = build_quality_report(document)

        self.assertFalse(report["passed"])
        self.assertIn("ocr_confidence_too_low", report["failures"])

    def test_short_document_is_blocked(self) -> None:
        report = build_quality_report(make_document("short"))

        self.assertFalse(report["passed"])
        self.assertIn("document_text_too_short", report["failures"])


if __name__ == "__main__":
    unittest.main()
