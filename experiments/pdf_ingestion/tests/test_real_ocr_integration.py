from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from experiments.pdf_ingestion.pdf_lab.ocr_backends import PaddleOCRBackend
from experiments.pdf_ingestion.pdf_lab.parser import PdfExperimentParser
from experiments.pdf_ingestion.pdf_lab.quality import build_quality_report


class RealPaddleOCRIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("RUN_PDF_OCR_INTEGRATION") == "1",
        "Set RUN_PDF_OCR_INTEGRATION=1 for the real PaddleOCR test",
    )
    def test_real_scanned_pdf_meets_quality_gate(self) -> None:
        fixture = os.getenv("PDF_OCR_FIXTURE")
        self.assertTrue(fixture, "Set PDF_OCR_FIXTURE to a scanned PDF path")

        parsed = PdfExperimentParser(ocr_backend=PaddleOCRBackend()).parse(Path(fixture))
        report = build_quality_report(parsed)

        output_directory = Path(
            os.getenv("PDF_OCR_OUTPUT_DIR", "experiments/pdf_ingestion/reports")
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        output_stem = Path(fixture).stem
        text_path = output_directory / f"{output_stem}-ocr.txt"
        parsed_path = output_directory / f"{output_stem}-parsed.json"
        quality_path = output_directory / f"{output_stem}-quality.json"
        text_path.write_text(parsed.plain_text, encoding="utf-8")
        parsed_path.write_text(
            json.dumps(parsed.to_ingestion_contract(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        quality_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"OCR text: {text_path.resolve()}")
        print(f"Parsed JSON: {parsed_path.resolve()}")
        print(f"Quality report: {quality_path.resolve()}")

        self.assertTrue(parsed.plain_text.strip())
        self.assertTrue(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
