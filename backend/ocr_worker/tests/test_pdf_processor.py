from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from ocr_worker.pdf_processor import PdfOCRQualityError, process_pdf

try:
    import fitz
except ImportError:
    fitz = None


ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeOCRBackend:
    name = "FAKE_OCR"

    def __init__(self, *, confidence: float = 0.98) -> None:
        self.confidence = confidence
        self.calls: list[int] = []

    def recognize_page(self, document_path: Path, page_index: int) -> list[dict]:
        self.calls.append(page_index)
        return [
            {
                "type": "paragraph",
                "text": (
                    "OCR recovered a scanned resume containing Python, RAG, "
                    "LangGraph, retrieval evaluation, and production deployment experience."
                ),
                "page_number": page_index + 1,
                "bbox": [10.0, 10.0, 500.0, 50.0],
                "source": "OCR",
                "confidence": self.confidence,
            }
        ]


@unittest.skipIf(fitz is None, "PyMuPDF is not installed")
class OCRPdfProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_scanned_pdf(self) -> Path:
        path = self.root / "scanned.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_image(page.rect, stream=ONE_PIXEL_PNG)
        document.save(path)
        document.close()
        return path

    def test_scanned_page_produces_ingestion_contract(self) -> None:
        backend = FakeOCRBackend()

        parsed, quality = process_pdf(self.create_scanned_pdf(), backend)

        self.assertEqual(backend.calls, [0])
        self.assertTrue(quality["passed"])
        self.assertEqual(quality["ocr_processed_pages"], [1])
        self.assertEqual(parsed["metadata"]["parser"], "PYMUPDF_PADDLEOCR")
        self.assertIn("LangGraph", parsed["plain_text"])

    def test_low_confidence_ocr_does_not_reach_chunking(self) -> None:
        backend = FakeOCRBackend(confidence=0.25)

        with self.assertRaises(PdfOCRQualityError) as context:
            process_pdf(self.create_scanned_pdf(), backend)

        self.assertIn("ocr_confidence_too_low", context.exception.report["failures"])


if __name__ == "__main__":
    unittest.main()
