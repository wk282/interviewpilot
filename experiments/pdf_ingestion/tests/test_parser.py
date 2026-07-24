from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.pdf_ingestion.pdf_lab.contracts import PageKind, TextBlock
from experiments.pdf_ingestion.pdf_lab.parser import (
    InvalidPdfError,
    OCRRequiredError,
    PdfExperimentParser,
    PdfLimitError,
)

try:
    import fitz
except ImportError:
    fitz = None


class FakeOCRBackend:
    name = "FAKE_OCR"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def recognize_page(self, document_path: Path, page_index: int) -> list[TextBlock]:
        self.calls.append(page_index)
        return [
            TextBlock(
                block_type="paragraph",
                text="OCR recovered technical interview content from scanned page.",
                source="OCR",
                confidence=0.98,
            )
        ]


@unittest.skipIf(fitz is None, "PyMuPDF is not installed")
class PdfExperimentParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_pdf(self, filename: str, page_texts: list[str | None]) -> Path:
        path = self.root / filename
        document = fitz.open()
        for text in page_texts:
            page = document.new_page()
            if text:
                page.insert_textbox(
                    fitz.Rect(50, 50, 540, 790),
                    text,
                    fontname="helv",
                    fontsize=11,
                )
        document.save(path)
        document.close()
        return path

    def test_native_text_pdf_produces_ingestion_contract(self) -> None:
        expected = (
            "Vector retrieval and BM25 retrieval provide complementary signals. "
            "The system evaluates Recall at K, MRR, and NDCG before production rollout."
        )
        path = self.create_pdf("native.pdf", [expected])

        parsed = PdfExperimentParser().parse(path)
        contract = parsed.to_ingestion_contract()

        self.assertEqual(parsed.pages[0].kind, PageKind.TEXT)
        self.assertFalse(parsed.pages[0].used_ocr)
        self.assertIn("Vector retrieval", contract["plain_text"])
        self.assertEqual(contract["metadata"]["page_count"], 1)
        self.assertTrue(contract["blocks"])

    def test_scanned_page_uses_injected_ocr_backend(self) -> None:
        path = self.create_pdf("scanned.pdf", [None])
        backend = FakeOCRBackend()

        parsed = PdfExperimentParser(ocr_backend=backend).parse(path)

        self.assertEqual(parsed.pages[0].kind, PageKind.SCANNED)
        self.assertTrue(parsed.pages[0].used_ocr)
        self.assertEqual(backend.calls, [0])
        self.assertIn("OCR recovered", parsed.plain_text)

    def test_scanned_page_fails_without_ocr_backend(self) -> None:
        path = self.create_pdf("scanned.pdf", [None])

        with self.assertRaises(OCRRequiredError):
            PdfExperimentParser().parse(path)

    def test_page_limit_is_enforced_before_parsing(self) -> None:
        path = self.create_pdf("two-pages.pdf", ["first page content", "second page content"])

        with self.assertRaises(PdfLimitError):
            PdfExperimentParser(max_pages=1).parse(path)

    def test_non_pdf_signature_is_rejected(self) -> None:
        path = self.root / "fake.pdf"
        path.write_text("not a PDF", encoding="utf-8")

        with self.assertRaises(InvalidPdfError):
            PdfExperimentParser().parse(path)


if __name__ == "__main__":
    unittest.main()
