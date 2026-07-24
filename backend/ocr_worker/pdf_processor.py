from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from ocr_worker.logging_config import logger


class OCRBackend(Protocol):
    name: str

    def recognize_page(self, document_path: Path, page_index: int) -> list[dict[str, Any]]:
        """Return OCR blocks for a zero-based page index."""


class PdfOCRQualityError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.report = report


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _printable_ratio(text: str) -> float:
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return 1.0
    return sum(character.isprintable() for character in characters) / len(characters)


def _image_coverage(page: Any) -> float:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    covered_area = 0.0
    seen_xrefs: set[int] = set()
    for image in page.get_images(full=True):
        xref = int(image[0])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        for rectangle in page.get_image_rects(xref):
            covered_area += max(float(rectangle.width), 0.0) * max(
                float(rectangle.height), 0.0
            )
    return min(1.0, covered_area / page_area)


def _page_kind(character_count: int, image_coverage: float, printable_ratio: float) -> str:
    if character_count == 0 and image_coverage < 0.05:
        return "BLANK"
    usable = character_count >= 40 and printable_ratio >= 0.90
    strong = character_count >= 120 and printable_ratio >= 0.90
    if strong:
        return "TEXT"
    if usable and image_coverage >= 0.35:
        return "MIXED"
    if usable:
        return "TEXT"
    return "SCANNED"


def _native_blocks(page: Any, page_number: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in page.get_text("dict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            text = "".join(
                str(span.get("text") or "") for span in line.get("spans", [])
            ).strip()
            if text:
                lines.append(text)
        text = _normalize_text("\n".join(lines))
        if text:
            result.append(
                {
                    "type": "paragraph",
                    "text": text,
                    "page_number": page_number,
                    "bbox": [float(value) for value in block.get("bbox", [])],
                    "source": "NATIVE",
                    "confidence": None,
                }
            )
    return result


def _deduplicate(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in blocks:
        normalized = "".join(str(block.get("text") or "").lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(block)
    return result


class PaddleOCRBackend:
    name = "PADDLE_OCR_2X"

    def __init__(self, *, render_scale: float = 2.5, lang: str = "ch") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise RuntimeError("PaddleOCR is not installed in the OCR worker") from error
        self.engine = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        self.render_scale = render_scale

    def recognize_page(self, document_path: Path, page_index: int) -> list[dict[str, Any]]:
        try:
            import cv2
            import fitz
            import numpy as np
        except ImportError as error:
            raise RuntimeError("OCR rendering dependencies are missing") from error

        with fitz.open(str(document_path)) as document:
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(self.render_scale, self.render_scale), alpha=False
            )
            image_bytes = pixmap.tobytes("png")
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise RuntimeError("Failed to render PDF page for OCR")

        raw_result = self.engine.ocr(image, cls=True)
        page_result = raw_result[0] if raw_result else []
        blocks: list[dict[str, Any]] = []
        for line in page_result or []:
            if not isinstance(line, (list, tuple)) or len(line) != 2:
                continue
            points, text_result = line
            if not isinstance(text_result, (list, tuple)) or len(text_result) != 2:
                continue
            text = str(text_result[0] or "").strip()
            confidence = float(text_result[1] or 0.0)
            if not text:
                continue
            x_values = [float(point[0]) for point in points]
            y_values = [float(point[1]) for point in points]
            blocks.append(
                {
                    "type": "paragraph",
                    "text": text,
                    "page_number": page_index + 1,
                    "bbox": [min(x_values), min(y_values), max(x_values), max(y_values)],
                    "source": "OCR",
                    "confidence": confidence,
                    "coordinate_space": "rendered_pixels",
                }
            )
        return sorted(
            blocks,
            key=lambda block: (block["bbox"][1], block["bbox"][0]),
        )


def process_pdf(
    path: Path,
    ocr_backend: OCRBackend,
    *,
    max_pages: int = 200,
    minimum_confidence: float = 0.75,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("PyMuPDF is not installed in the OCR worker") from error
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("File signature is not PDF")

    with fitz.open(str(path)) as document:
        if document.needs_pass:
            raise ValueError("Encrypted PDF requires a password")
        if document.page_count > max_pages:
            raise ValueError(f"PDF exceeds the {max_pages}-page OCR limit")

        all_blocks: list[dict[str, Any]] = []
        page_kinds: list[str] = []
        page_metrics: list[dict[str, Any]] = []
        ocr_processed_pages: list[int] = []
        failed_pages: list[int] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_number = page_index + 1
            native_blocks = _native_blocks(page, page_number)
            native_text = _normalize_text(
                "\n\n".join(block["text"] for block in native_blocks)
            )
            image_coverage = _image_coverage(page)
            printable_ratio = _printable_ratio(native_text)
            kind = _page_kind(len(native_text), image_coverage, printable_ratio)
            page_kinds.append(kind)
            logger.info(
                "PDF page classified | file=%s | page=%s | kind=%s | "
                "native_characters=%s | image_coverage=%.4f",
                path.name,
                page_number,
                kind,
                len(native_text),
                image_coverage,
            )

            if kind in {"SCANNED", "MIXED"}:
                logger.info(
                    "OCR page started | file=%s | page=%s | kind=%s",
                    path.name,
                    page_number,
                    kind,
                )
                ocr_blocks = ocr_backend.recognize_page(path, page_index)
                page_blocks = _deduplicate(
                    [*native_blocks, *ocr_blocks] if kind == "MIXED" else ocr_blocks
                )
                ocr_processed_pages.append(page_number)
                if not page_blocks:
                    failed_pages.append(page_number)
                logger.info(
                    "OCR page completed | file=%s | page=%s | blocks=%s",
                    path.name,
                    page_number,
                    len(ocr_blocks),
                )
            else:
                page_blocks = native_blocks
            all_blocks.extend(page_blocks)
            page_metrics.append(
                {
                    "page_number": page_number,
                    "kind": kind,
                    "native_character_count": len(native_text),
                    "image_coverage": round(image_coverage, 6),
                    "ocr_block_count": sum(
                        block.get("source") == "OCR" for block in page_blocks
                    ),
                }
            )

    plain_text = _normalize_text("\n\n".join(block["text"] for block in all_blocks))
    confidences = [
        float(block["confidence"])
        for block in all_blocks
        if block.get("source") == "OCR" and block.get("confidence") is not None
    ]
    average_confidence = sum(confidences) / len(confidences) if confidences else None
    failures: list[str] = []
    if len(plain_text) < 40:
        failures.append("document_text_too_short")
    if failed_pages:
        failures.append("ocr_page_has_no_text")
    if average_confidence is not None and average_confidence < minimum_confidence:
        failures.append("ocr_confidence_too_low")

    quality_report = {
        "passed": not failures,
        "failures": failures,
        "character_count": len(plain_text),
        "page_count": len(page_kinds),
        "page_kinds": page_kinds,
        "ocr_processed_pages": ocr_processed_pages,
        "ocr_failed_pages": failed_pages,
        "average_ocr_confidence": (
            round(average_confidence, 6) if average_confidence is not None else None
        ),
        "minimum_ocr_confidence": minimum_confidence,
        "page_metrics": page_metrics,
        "needs_ocr": False,
        "ocr_required_pages": [],
    }
    parsed = {
        "metadata": {
            "source_file": path.name,
            "parser": "PYMUPDF_PADDLEOCR",
            "parser_version": "1.0",
            "ocr_backend": ocr_backend.name,
            "page_count": len(page_kinds),
            "page_kinds": page_kinds,
            "ocr_processed_pages": ocr_processed_pages,
            "ocr_required_pages": [],
            "page_metrics": page_metrics,
        },
        "blocks": all_blocks,
        "plain_text": plain_text,
    }
    if failures:
        logger.error(
            "OCR quality gate failed | file=%s | failures=%s | report=%s",
            path.name,
            failures,
            quality_report,
        )
        raise PdfOCRQualityError(
            f"OCR quality gate failed: {', '.join(failures)}", quality_report
        )
    logger.info(
        "OCR quality gate passed | file=%s | characters=%s | pages=%s | "
        "average_confidence=%s",
        path.name,
        len(plain_text),
        len(page_kinds),
        quality_report["average_ocr_confidence"],
    )
    return parsed, quality_report
