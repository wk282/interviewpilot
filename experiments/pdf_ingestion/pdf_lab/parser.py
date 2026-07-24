from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .classifier import classify_page
from .contracts import (
    OCRBackend,
    PageObservation,
    ParsedDocument,
    ParsedPage,
    TextBlock,
)


class PdfExperimentError(ValueError):
    pass


class InvalidPdfError(PdfExperimentError):
    pass


class EncryptedPdfError(PdfExperimentError):
    pass


class PdfLimitError(PdfExperimentError):
    pass


class OCRRequiredError(PdfExperimentError):
    pass


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _printable_ratio(text: str) -> float:
    if not text:
        return 1.0
    return sum(character.isprintable() for character in text) / len(text)


def _native_blocks(page_dict: dict[str, Any]) -> list[TextBlock]:
    result: list[TextBlock] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        line_values: list[str] = []
        font_sizes: list[float] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            if text:
                line_values.append(text)
            font_sizes.extend(float(span.get("size") or 0.0) for span in spans)
        block_text = _normalize_text("\n".join(line_values))
        if not block_text:
            continue
        raw_bbox = block.get("bbox")
        bbox = tuple(float(value) for value in raw_bbox) if raw_bbox else None
        result.append(
            TextBlock(
                block_type="paragraph",
                text=block_text,
                bbox=bbox,  # type: ignore[arg-type]
                source="NATIVE",
                metadata={"max_font_size": max(font_sizes, default=0.0)},
            )
        )
    return result


def _image_coverage(page: Any) -> float:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    covered_area = 0.0
    seen_xrefs: set[int] = set()
    for image in page.get_images(full=True):
        xref = int(image[0])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        for rect in page.get_image_rects(xref):
            covered_area += max(float(rect.width), 0.0) * max(float(rect.height), 0.0)
    return min(1.0, covered_area / page_area)


def _deduplicate_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    result: list[TextBlock] = []
    seen: set[str] = set()
    for block in blocks:
        key = "".join(block.text.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(block)
    return result


class PdfExperimentParser:
    name = "PYMUPDF_PAGE_ROUTER"
    version = "0.1.0-experiment"

    def __init__(
        self,
        *,
        ocr_backend: OCRBackend | None = None,
        max_pages: int = 200,
        max_file_size_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.ocr_backend = ocr_backend
        self.max_pages = max_pages
        self.max_file_size_bytes = max_file_size_bytes

    def parse(self, path: Path) -> ParsedDocument:
        if not path.is_file():
            raise InvalidPdfError("PDF file does not exist")
        if path.stat().st_size > self.max_file_size_bytes:
            raise PdfLimitError("PDF exceeds the experimental file-size limit")
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise InvalidPdfError("File signature is not PDF")

        try:
            import fitz
        except ImportError as error:
            raise RuntimeError("Install PyMuPDF for the PDF experiment") from error

        try:
            document = fitz.open(path)
        except Exception as error:
            raise InvalidPdfError(f"PyMuPDF cannot open the PDF: {error}") from error

        try:
            if document.needs_pass:
                raise EncryptedPdfError("Encrypted PDF requires a password")
            if document.page_count > self.max_pages:
                raise PdfLimitError("PDF exceeds the experimental page limit")

            pages = [self._parse_page(path, document, index) for index in range(document.page_count)]
        finally:
            document.close()

        return ParsedDocument(
            source_file=path.name,
            parser_name=self.name,
            parser_version=self.version,
            pages=pages,
            metadata={
                "ocr_backend": self.ocr_backend.name if self.ocr_backend else None,
                "selective_ocr": True,
            },
        )

    def _parse_page(self, path: Path, document: Any, page_index: int) -> ParsedPage:
        page = document.load_page(page_index)
        page_dict = page.get_text("dict", sort=True)
        native_blocks = _native_blocks(page_dict)
        native_text = _normalize_text("\n\n".join(block.text for block in native_blocks))
        observation = PageObservation(
            native_character_count=len(native_text),
            text_block_count=len(native_blocks),
            image_coverage=_image_coverage(page),
            printable_ratio=_printable_ratio(native_text),
        )
        kind = classify_page(observation)
        blocks = native_blocks
        used_ocr = False

        if kind.value in {"SCANNED", "MIXED"}:
            if self.ocr_backend is None:
                raise OCRRequiredError(
                    f"Page {page_index + 1} requires OCR but no OCR backend is configured"
                )
            ocr_blocks = self.ocr_backend.recognize_page(path, page_index)
            blocks = (
                _deduplicate_blocks([*native_blocks, *ocr_blocks])
                if kind.value == "MIXED"
                else _deduplicate_blocks(ocr_blocks)
            )
            used_ocr = True

        plain_text = _normalize_text("\n\n".join(block.text for block in blocks))
        return ParsedPage(
            page_number=page_index + 1,
            kind=kind,
            blocks=blocks,
            plain_text=plain_text,
            observation=observation,
            used_ocr=used_ocr,
        )

