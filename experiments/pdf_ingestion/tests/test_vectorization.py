from __future__ import annotations

import unittest

from experiments.pdf_ingestion.pdf_lab.vectorization import (
    chunk_text_for_probe,
    validate_vectorization_contract,
)


class FakeEmbeddingBackend:
    name = "FAKE_EMBEDDING"

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * self.dimensions for _ in texts]


class VectorizationContractTest(unittest.TestCase):
    def test_probe_chunking_preserves_overlap(self) -> None:
        chunks = chunk_text_for_probe("abcdefghij", chunk_size=6, overlap=2)

        self.assertEqual(chunks, ["abcdef", "efghij"])

    def test_every_chunk_receives_a_1024_dimension_vector(self) -> None:
        result = validate_vectorization_contract(
            ["first child chunk", "second child chunk"],
            FakeEmbeddingBackend(),
        )

        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(result.vector_count, 2)
        self.assertEqual(result.dimensions, 1024)

    def test_wrong_embedding_dimensions_fail_the_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 1024"):
            validate_vectorization_contract(
                ["child chunk"],
                FakeEmbeddingBackend(dimensions=2048),
            )

    def test_empty_chunks_are_not_sent_to_embedding(self) -> None:
        with self.assertRaisesRegex(ValueError, "No non-empty chunks"):
            validate_vectorization_contract(["", "  "], FakeEmbeddingBackend())


if __name__ == "__main__":
    unittest.main()
