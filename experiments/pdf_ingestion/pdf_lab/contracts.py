from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class PageKind(str, Enum):
    TEXT = "TEXT"
    SCANNED = "SCANNED"
    MIXED = "MIXED"


@dataclass(frozen=True)
class PageObservation:
    native_character_count: int
    text_block_count: int
    image_coverage: float
    printable_ratio: float


@dataclass
class TextBlock:
    block_type: str
    text: str
    bbox: tuple[float, float, float, float] | None = None
    source: str = "NATIVE"
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedPage:
    page_number: int
    kind: PageKind
    blocks: list[TextBlock]
    plain_text: str
    observation: PageObservation
    used_ocr: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass
class ParsedDocument:
    source_file: str
    parser_name: str
    parser_version: str
    pages: list[ParsedPage]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocks(self) -> list[TextBlock]:
        return [block for page in self.pages for block in page.blocks]

    @property
    def plain_text(self) -> str:
        return "\n\n".join(
            page.plain_text.strip() for page in self.pages if page.plain_text.strip()
        )

    def to_ingestion_contract(self) -> dict[str, Any]:
        return {
            "metadata": {
                "source_file": self.source_file,
                "parser": self.parser_name,
                "parser_version": self.parser_version,
                "page_count": len(self.pages),
                **self.metadata,
            },
            "blocks": [block.to_dict() for block in self.blocks],
            "plain_text": self.plain_text,
            "pages": [page.to_dict() for page in self.pages],
        }


class OCRBackend(Protocol):
    name: str

    def recognize_page(self, document_path: Path, page_index: int) -> list[TextBlock]:
        """Return OCR blocks for a zero-based PDF page index."""

