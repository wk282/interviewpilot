from __future__ import annotations

from .contracts import PageKind, PageObservation


MIN_NATIVE_TEXT_CHARACTERS = 40
STRONG_NATIVE_TEXT_CHARACTERS = 120
MIXED_IMAGE_COVERAGE = 0.35
SCANNED_IMAGE_COVERAGE = 0.60
MIN_PRINTABLE_RATIO = 0.90


def classify_page(observation: PageObservation) -> PageKind:
    """Classify one page so OCR is used only where native text is insufficient."""
    has_usable_text = (
        observation.native_character_count >= MIN_NATIVE_TEXT_CHARACTERS
        and observation.printable_ratio >= MIN_PRINTABLE_RATIO
    )
    has_strong_text = (
        observation.native_character_count >= STRONG_NATIVE_TEXT_CHARACTERS
        and observation.printable_ratio >= MIN_PRINTABLE_RATIO
    )

    if has_strong_text and observation.image_coverage < SCANNED_IMAGE_COVERAGE:
        return PageKind.TEXT
    if has_usable_text and observation.image_coverage >= MIXED_IMAGE_COVERAGE:
        return PageKind.MIXED
    if has_usable_text:
        return PageKind.TEXT
    return PageKind.SCANNED

