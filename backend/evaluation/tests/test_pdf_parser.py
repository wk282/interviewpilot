from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from app.services.document_parsers import PdfParser, build_quality_report, parser_for

try:
    import fitz
except ImportError:
    fitz = None


ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@unittest.skipIf(fitz is None, "PyMuPDF is not installed")
class ProductionPdfParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def save_document(self, document, filename: str) -> Path:
        path = self.root / filename
        document.save(path)
        document.close()
        return path

    def test_text_pdf_is_ready_for_chunking(self) -> None:
        text = (
            "Vector retrieval and BM25 retrieval provide complementary signals. "
            "The production system evaluates Recall at K, MRR, and NDCG before rollout. "
            "Every child chunk must receive one valid 1024 dimension embedding vector."
        )
        document = fitz.open()
        page = document.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 540, 790), text, fontname="helv", fontsize=11)
        path = self.save_document(document, "native.pdf")

        parsed = PdfParser().parse(path)
        quality = build_quality_report(parsed)

        self.assertEqual(parsed["metadata"]["page_kinds"], ["TEXT"])
        self.assertFalse(quality["needs_ocr"])
        self.assertFalse(quality["empty"])
        self.assertIn("Vector retrieval", parsed["plain_text"])
        self.assertIsInstance(parser_for(path), PdfParser)

    def test_blank_page_does_not_trigger_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_textbox(
            fitz.Rect(50, 50, 540, 790),
            "This native PDF page contains enough readable text to pass the production parser. "
            "A trailing blank page should not force the complete document into the OCR queue.",
            fontname="helv",
            fontsize=11,
        )
        document.new_page()
        path = self.save_document(document, "blank-page.pdf")

        parsed = PdfParser().parse(path)
        quality = build_quality_report(parsed)

        self.assertEqual(parsed["metadata"]["page_kinds"], ["TEXT", "BLANK"])
        self.assertFalse(quality["needs_ocr"])

    def test_image_only_page_waits_for_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_image(page.rect, stream=ONE_PIXEL_PNG)
        path = self.save_document(document, "scanned.pdf")

        parsed = PdfParser().parse(path)
        quality = build_quality_report(parsed)

        self.assertEqual(parsed["metadata"]["page_kinds"], ["SCANNED"])
        self.assertTrue(quality["needs_ocr"])
        self.assertEqual(quality["ocr_required_pages"], [1])
        self.assertTrue(quality["empty"])


if __name__ == "__main__":
    unittest.main()
