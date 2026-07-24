from __future__ import annotations

from dataclasses import asdict, dataclass

from .contracts import ParsedDocument


@dataclass(frozen=True)
class QualityThresholds:
    minimum_document_characters: int = 40
    maximum_empty_page_rate: float = 0.05
    maximum_replacement_character_rate: float = 0.001
    minimum_ocr_confidence: float = 0.75


def build_quality_report(
    document: ParsedDocument,
    thresholds: QualityThresholds | None = None,
) -> dict:
    thresholds = thresholds or QualityThresholds()
    page_count = len(document.pages)
    empty_page_count = sum(not page.plain_text.strip() for page in document.pages)
    empty_page_rate = empty_page_count / page_count if page_count else 1.0
    text = document.plain_text
    replacement_rate = text.count("\ufffd") / len(text) if text else 0.0
    ocr_confidences = [
        block.confidence
        for page in document.pages
        for block in page.blocks
        if block.source == "OCR" and block.confidence is not None
    ]
    average_ocr_confidence = (
        sum(ocr_confidences) / len(ocr_confidences) if ocr_confidences else None
    )
    failures: list[str] = []
    if len(text) < thresholds.minimum_document_characters:
        failures.append("document_text_too_short")
    if empty_page_rate > thresholds.maximum_empty_page_rate:
        failures.append("too_many_empty_pages")
    if replacement_rate > thresholds.maximum_replacement_character_rate:
        failures.append("garbled_text_rate_too_high")
    if (
        average_ocr_confidence is not None
        and average_ocr_confidence < thresholds.minimum_ocr_confidence
    ):
        failures.append("ocr_confidence_too_low")

    return {
        "passed": not failures,
        "failures": failures,
        "thresholds": asdict(thresholds),
        "metrics": {
            "page_count": page_count,
            "character_count": len(text),
            "empty_page_count": empty_page_count,
            "empty_page_rate": round(empty_page_rate, 6),
            "replacement_character_rate": round(replacement_rate, 6),
            "ocr_page_count": sum(page.used_ocr for page in document.pages),
            "average_ocr_confidence": (
                round(average_ocr_confidence, 6)
                if average_ocr_confidence is not None
                else None
            ),
        },
    }

