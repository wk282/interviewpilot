from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class EmbeddingBackend(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector for every input text."""


@dataclass(frozen=True)
class VectorizationProbeResult:
    backend: str
    chunk_count: int
    vector_count: int
    dimensions: int


def chunk_text_for_probe(
    text: str,
    *,
    chunk_size: int = 350,
    overlap: int = 50,
) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid probe chunk configuration")
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        chunk = normalized[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(normalized):
            break
        start += chunk_size - overlap
    return chunks


def validate_vectorization_contract(
    chunks: list[str],
    backend: EmbeddingBackend,
    *,
    expected_dimensions: int = 1024,
) -> VectorizationProbeResult:
    normalized_chunks = [text.strip() for text in chunks if text.strip()]
    if not normalized_chunks:
        raise ValueError("No non-empty chunks are available for embedding")
    vectors = backend.embed(normalized_chunks)
    if len(vectors) != len(normalized_chunks):
        raise ValueError("Embedding result count does not match chunk count")
    for index, vector in enumerate(vectors):
        if len(vector) != expected_dimensions:
            raise ValueError(
                f"Vector {index} has {len(vector)} dimensions; expected {expected_dimensions}"
            )
        if not all(math.isfinite(float(value)) for value in vector):
            raise ValueError(f"Vector {index} contains a non-finite value")
    return VectorizationProbeResult(
        backend=backend.name,
        chunk_count=len(normalized_chunks),
        vector_count=len(vectors),
        dimensions=expected_dimensions,
    )
