from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import Any

from markdown_it import MarkdownIt


class UnsupportedParserError(ValueError):
    pass


PDF_MIN_NATIVE_TEXT_CHARACTERS = 40
PDF_STRONG_NATIVE_TEXT_CHARACTERS = 120
PDF_MIXED_IMAGE_COVERAGE = 0.35
PDF_BLANK_IMAGE_COVERAGE = 0.05
PDF_MIN_PRINTABLE_RATIO = 0.90


class DocumentParser(ABC):
    name: str
    version: str = "1.0"

    @abstractmethod
    def parse(self, path: Path) -> dict[str, Any]:
        raise NotImplementedError


class MarkdownParser(DocumentParser):
    name = "MARKDOWN_IT"

    def __init__(self) -> None:
        self.markdown = MarkdownIt("commonmark")

    def parse(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8-sig")
        tokens = self.markdown.parse(text)
        blocks: list[dict[str, Any]] = []
        heading_level: int | None = None

        for index, token in enumerate(tokens):
            if token.type == "heading_open":
                heading_level = int(token.tag[1])
                continue
            if token.type == "inline" and heading_level is not None:
                blocks.append({"type": "heading", "level": heading_level, "text": token.content})
                heading_level = None
                continue
            if token.type == "inline" and index > 0 and tokens[index - 1].type == "paragraph_open":
                blocks.append({"type": "paragraph", "text": token.content})
            elif token.type in {"fence", "code_block"}:
                blocks.append(
                    {
                        "type": "code",
                        "language": token.info.strip() or None,
                        "text": token.content,
                    }
                )

        return {
            "metadata": {"source_file": path.name, "parser": self.name, "parser_version": self.version},
            "blocks": blocks,
            "plain_text": text,
        }


class TextParser(DocumentParser):
    name = "PLAIN_TEXT"

    def parse(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8-sig")
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        return {
            "metadata": {"source_file": path.name, "parser": self.name, "parser_version": self.version},
            "blocks": [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs],
            "plain_text": text,
        }


class DocxParser(DocumentParser):
    name = "PYTHON_DOCX"

    @staticmethod
    def _xml_text(element: Any) -> str:
        return "".join(
            node.text or ""
            for node in element.iter()
            if node.tag.rsplit("}", 1)[-1] == "t"
        ).strip()

    def parse(self, path: Path) -> dict[str, Any]:
        try:
            from docx import Document as load_docx
            from docx.table import Table
            from docx.text.paragraph import Paragraph
        except ImportError as error:
            raise RuntimeError("DOCX parser dependency is missing: install python-docx") from error

        document = load_docx(str(path))
        blocks: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for element in document.element.body.iterchildren():
            element_type = element.tag.rsplit("}", 1)[-1]
            if element_type == "p":
                paragraph = Paragraph(element, document)
                # paragraph.text omits text stored in Word text boxes and drawings.
                text = self._xml_text(element)
                if not text:
                    continue
                style_name = paragraph.style.name if paragraph.style else ""
                normalized_style = style_name.lower()
                if normalized_style.startswith("heading") or style_name.startswith("标题"):
                    level_match = re.search(r"(\d+)$", style_name)
                    blocks.append(
                        {
                            "type": "heading",
                            "level": int(level_match.group(1)) if level_match else 1,
                            "text": text,
                        }
                    )
                elif "list" in normalized_style or "列表" in style_name:
                    blocks.append({"type": "list_item", "text": text})
                else:
                    blocks.append({"type": "paragraph", "text": text})
                text_parts.append(text)
            elif element_type == "tbl":
                table = Table(element, document)
                rows = [
                    [self._xml_text(cell._tc) for cell in row.cells]
                    for row in table.rows
                ]
                rows = [row for row in rows if any(row)]
                if not rows:
                    continue
                table_text = "\n".join(" | ".join(row) for row in rows)
                blocks.append({"type": "table", "rows": rows, "text": table_text})
                text_parts.append(table_text)
            else:
                # Content controls and other Word containers may hold resume text.
                text = self._xml_text(element)
                if text:
                    blocks.append({"type": "paragraph", "text": text})
                    text_parts.append(text)

        seen_parts = set(text_parts)
        for section in document.sections:
            stories = (
                section.header,
                section.first_page_header,
                section.even_page_header,
                section.footer,
                section.first_page_footer,
                section.even_page_footer,
            )
            for story in stories:
                for paragraph in story.paragraphs:
                    text = self._xml_text(paragraph._p)
                    if text and text not in seen_parts:
                        blocks.append({"type": "paragraph", "text": text})
                        text_parts.append(text)
                        seen_parts.add(text)

        return {
            "metadata": {
                "source_file": path.name,
                "parser": self.name,
                "parser_version": self.version,
            },
            "blocks": blocks,
            "plain_text": "\n\n".join(text_parts),
        }


def _pdf_printable_ratio(text: str) -> float:
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return 1.0
    return sum(character.isprintable() for character in characters) / len(characters)


def _pdf_page_kind(
    *,
    native_character_count: int,
    image_coverage: float,
    printable_ratio: float,
) -> str:
    if native_character_count == 0 and image_coverage < PDF_BLANK_IMAGE_COVERAGE:
        return "BLANK"
    has_usable_text = (
        native_character_count >= PDF_MIN_NATIVE_TEXT_CHARACTERS
        and printable_ratio >= PDF_MIN_PRINTABLE_RATIO
    )
    has_strong_text = (
        native_character_count >= PDF_STRONG_NATIVE_TEXT_CHARACTERS
        and printable_ratio >= PDF_MIN_PRINTABLE_RATIO
    )
    if has_strong_text:
        return "TEXT"
    if has_usable_text and image_coverage >= PDF_MIXED_IMAGE_COVERAGE:
        return "MIXED"
    if has_usable_text:
        return "TEXT"
    return "SCANNED"


def _pdf_image_coverage(page: Any) -> float:
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


def _pdf_native_blocks(page: Any, page_number: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    page_dict = page.get_text("dict", sort=True)
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        font_sizes: list[float] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            if text:
                lines.append(text)
            font_sizes.extend(float(span.get("size") or 0.0) for span in spans)
        block_text = "\n".join(lines).strip()
        if not block_text:
            continue
        result.append(
            {
                "type": "paragraph",
                "text": block_text,
                "page_number": page_number,
                "bbox": [float(value) for value in block.get("bbox", [])],
                "source": "NATIVE",
                "max_font_size": max(font_sizes, default=0.0),
            }
        )
    return result


class PdfParser(DocumentParser):
    name = "PYMUPDF_TEXT"
    version = "1.0"

    def __init__(self, max_pages: int = 200) -> None:
        self.max_pages = max_pages

    def parse(self, path: Path) -> dict[str, Any]:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError("File signature is not PDF")
        try:
            import fitz
        except ImportError as error:
            raise RuntimeError("PDF parser dependency is missing: install PyMuPDF") from error
        try:
            document = fitz.open(str(path))
        except Exception as error:
            raise ValueError(f"PyMuPDF cannot open the PDF: {error}") from error

        try:
            if document.needs_pass:
                raise ValueError("Encrypted PDF requires a password")
            if document.page_count > self.max_pages:
                raise ValueError(f"PDF exceeds the {self.max_pages}-page limit")

            blocks: list[dict[str, Any]] = []
            text_parts: list[str] = []
            page_kinds: list[str] = []
            ocr_required_pages: list[int] = []
            page_metrics: list[dict[str, Any]] = []
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                page_blocks = _pdf_native_blocks(page, page_number)
                page_text = "\n\n".join(block["text"] for block in page_blocks).strip()
                image_coverage = _pdf_image_coverage(page)
                printable_ratio = _pdf_printable_ratio(page_text)
                kind = _pdf_page_kind(
                    native_character_count=len(page_text),
                    image_coverage=image_coverage,
                    printable_ratio=printable_ratio,
                )
                page_kinds.append(kind)
                if kind in {"SCANNED", "MIXED"}:
                    ocr_required_pages.append(page_number)
                blocks.extend(page_blocks)
                if page_text:
                    text_parts.append(page_text)
                page_metrics.append(
                    {
                        "page_number": page_number,
                        "kind": kind,
                        "native_character_count": len(page_text),
                        "text_block_count": len(page_blocks),
                        "image_coverage": round(image_coverage, 6),
                        "printable_ratio": round(printable_ratio, 6),
                    }
                )
        finally:
            document.close()

        return {
            "metadata": {
                "source_file": path.name,
                "parser": self.name,
                "parser_version": self.version,
                "page_count": len(page_kinds),
                "page_kinds": page_kinds,
                "ocr_required_pages": ocr_required_pages,
                "page_metrics": page_metrics,
            },
            "blocks": blocks,
            "plain_text": "\n\n".join(text_parts),
        }


def parser_for(path: Path) -> DocumentParser:
    extension = path.suffix.lower()
    if extension == ".md":
        return MarkdownParser()
    if extension == ".txt":
        return TextParser()
    if extension == ".docx":
        return DocxParser()
    if extension == ".pdf":
        return PdfParser()
    raise UnsupportedParserError(f"Parser not implemented for {extension}")


def build_quality_report(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("plain_text", "")
    blocks = parsed.get("blocks", [])
    metadata = parsed.get("metadata", {})
    length = len(text)
    replacement_count = text.count("\ufffd")
    ocr_required_pages = list(metadata.get("ocr_required_pages", []))
    return {
        "character_count": length,
        "block_count": len(blocks),
        "heading_count": sum(1 for block in blocks if block.get("type") == "heading"),
        "garbled_ratio": replacement_count / length if length else 0.0,
        "empty": not bool(text.strip()),
        "needs_ocr": bool(ocr_required_pages),
        "ocr_required_pages": ocr_required_pages,
        "page_count": metadata.get("page_count"),
        "page_kinds": list(metadata.get("page_kinds", [])),
        "page_metrics": list(metadata.get("page_metrics", [])),
        "needs_vlm_fallback": bool(ocr_required_pages),
    }
