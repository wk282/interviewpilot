from __future__ import annotations


class OpenAICompatibleEmbeddingBackend:
    """External embedding adapter used only by an opt-in integration test."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int = 1024,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the openai package for the embedding probe") from error
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=45.0, max_retries=0)
        self.model = model
        self.dimensions = dimensions
        self.name = f"OPENAI_COMPATIBLE:{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
