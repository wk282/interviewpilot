from __future__ import annotations

import json
import uuid
from typing import Any

import requests

from app.core.config import settings


class OpenSearchBM25Store:
    """OpenSearch adapter for BM25 chunk indexing and retrieval."""

    def __init__(self) -> None:
        if not settings.OPENSEARCH_URL:
            raise RuntimeError("OPENSEARCH_URL is not configured")
        self.base_url = settings.OPENSEARCH_URL.rstrip("/")
        self.index_name = settings.OPENSEARCH_INDEX_NAME
        self.auth = None
        if settings.OPENSEARCH_USERNAME:
            self.auth = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD or "")

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            auth=self.auth,
            timeout=settings.OPENSEARCH_TIMEOUT_SECONDS,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def ensure_index(self) -> None:
        exists_response = requests.head(
            f"{self.base_url}/{self.index_name}",
            auth=self.auth,
            timeout=settings.OPENSEARCH_TIMEOUT_SECONDS,
        )
        if exists_response.status_code == 200:
            return
        if exists_response.status_code != 404:
            exists_response.raise_for_status()

        response = requests.put(
            f"{self.base_url}/{self.index_name}",
            auth=self.auth,
            timeout=settings.OPENSEARCH_TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"},
            json={
                "settings": {"index": {"similarity": {"default": {"type": "BM25"}}}},
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "workspace_id": {"type": "keyword"},
                        "knowledge_base_id": {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "document_version_id": {"type": "keyword"},
                        "chunk_type": {"type": "keyword"},
                        "content": {
                            "type": "text",
                            "analyzer": "cjk",
                            "search_analyzer": "cjk",
                        },
                    }
                },
            },
        )
        if response.status_code == 400:
            error_type = response.json().get("error", {}).get("type")
            if error_type == "resource_already_exists_exception":
                return
        response.raise_for_status()

    def index_chunks(self, chunks: list[dict[str, str]]) -> None:
        if not chunks:
            return
        self.ensure_index()
        lines: list[str] = []
        for chunk in chunks:
            lines.append(
                json.dumps(
                    {"index": {"_index": self.index_name, "_id": chunk["chunk_id"]}},
                    ensure_ascii=False,
                )
            )
            lines.append(json.dumps(chunk, ensure_ascii=False))
        payload = "\n".join(lines) + "\n"
        response = self._request(
            "POST",
            "/_bulk?refresh=wait_for",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
        )
        if response.json().get("errors"):
            raise RuntimeError("OpenSearch bulk indexing failed")

    def search(
        self,
        query: str,
        workspace_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        size: int,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple[uuid.UUID, float]]:
        self.ensure_index()
        filters: list[dict[str, Any]] = [
            {"term": {"workspace_id": str(workspace_id)}},
            {"term": {"knowledge_base_id": str(knowledge_base_id)}},
            {"term": {"chunk_type": "CHILD"}},
        ]
        if document_ids:
            filters.append(
                {"terms": {"document_id": [str(document_id) for document_id in document_ids]}}
            )
        body = {
            "size": size,
            "_source": False,
            "query": {
                "bool": {
                    "filter": filters,
                    "must": [{"match": {"content": {"query": query, "operator": "or"}}}],
                }
            },
        }
        hits = self._request("POST", f"/{self.index_name}/_search", json=body).json()
        return [
            (uuid.UUID(hit["_id"]), float(hit.get("_score") or 0.0))
            for hit in hits.get("hits", {}).get("hits", [])
        ]

    def score_candidates(
        self,
        query: str,
        workspace_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, float]:
        if not chunk_ids:
            return {}
        self.ensure_index()
        body = {
            "size": len(chunk_ids),
            "_source": False,
            "query": {
                "bool": {
                    "filter": [
                        {"ids": {"values": [str(chunk_id) for chunk_id in chunk_ids]}},
                        {"term": {"workspace_id": str(workspace_id)}},
                        {"term": {"knowledge_base_id": str(knowledge_base_id)}},
                        {"term": {"chunk_type": "CHILD"}},
                    ],
                    "must": [{"match": {"content": {"query": query, "operator": "or"}}}],
                }
            },
        }
        hits = self._request("POST", f"/{self.index_name}/_search", json=body).json()
        return {
            uuid.UUID(hit["_id"]): float(hit.get("_score") or 0.0)
            for hit in hits.get("hits", {}).get("hits", [])
        }

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        if not settings.OPENSEARCH_URL:
            return
        self._request(
            "POST",
            f"/{self.index_name}/_delete_by_query",
            json={"query": {"term": {"document_id": str(document_id)}}},
        )

    def delete_by_knowledge_base(self, knowledge_base_id: uuid.UUID) -> None:
        if not settings.OPENSEARCH_URL:
            return
        self._request(
            "POST",
            f"/{self.index_name}/_delete_by_query",
            json={"query": {"term": {"knowledge_base_id": str(knowledge_base_id)}}},
        )
