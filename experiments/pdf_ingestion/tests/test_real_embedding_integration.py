from __future__ import annotations

import os
import unittest
from pathlib import Path

from experiments.pdf_ingestion.pdf_lab.embedding_backends import (
    OpenAICompatibleEmbeddingBackend,
)
from experiments.pdf_ingestion.pdf_lab.parser import PdfExperimentParser
from experiments.pdf_ingestion.pdf_lab.quality import build_quality_report
from experiments.pdf_ingestion.pdf_lab.vectorization import (
    chunk_text_for_probe,
    validate_vectorization_contract,
)


class RealEmbeddingIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("RUN_PDF_EMBEDDING_INTEGRATION") == "1",
        "Set RUN_PDF_EMBEDDING_INTEGRATION=1 for the paid embedding test",
    )
    def test_pdf_text_produces_complete_1024_dimension_vectors(self) -> None:
        fixture = os.getenv("PDF_EMBEDDING_FIXTURE")
        api_key = os.getenv("PDF_EMBEDDING_API_KEY")
        base_url = os.getenv("PDF_EMBEDDING_BASE_URL")
        model = os.getenv("PDF_EMBEDDING_MODEL")
        self.assertTrue(fixture, "Set PDF_EMBEDDING_FIXTURE to a native text PDF")
        self.assertTrue(api_key, "Set PDF_EMBEDDING_API_KEY")
        self.assertTrue(base_url, "Set PDF_EMBEDDING_BASE_URL")
        self.assertTrue(model, "Set PDF_EMBEDDING_MODEL")

        parsed = PdfExperimentParser().parse(Path(fixture))
        quality = build_quality_report(parsed)
        self.assertTrue(quality["passed"], quality)
        chunks = chunk_text_for_probe(parsed.plain_text)
        backend = OpenAICompatibleEmbeddingBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            dimensions=1024,
        )

        result = validate_vectorization_contract(chunks, backend)

        self.assertEqual(result.chunk_count, result.vector_count)
        self.assertEqual(result.dimensions, 1024)


if __name__ == "__main__":
    unittest.main()
