from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import Any

from markdown_it import MarkdownIt


class UnsupportedParserError(ValueError):
    pass


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


def parser_for(path: Path) -> DocumentParser:
    extension = path.suffix.lower()
    if extension == ".md":
        return MarkdownParser()
    if extension == ".txt":
        return TextParser()
    if extension == ".docx":
        return DocxParser()
    raise UnsupportedParserError(f"Parser not implemented for {extension}")


def build_quality_report(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("plain_text", "")
    blocks = parsed.get("blocks", [])
    length = len(text)
    replacement_count = text.count("\ufffd")
    return {
        "character_count": length,
        "block_count": len(blocks),
        "heading_count": sum(1 for block in blocks if block.get("type") == "heading"),
        "garbled_ratio": replacement_count / length if length else 0.0,
        "empty": not bool(text.strip()),
        "needs_vlm_fallback": False,
    }
