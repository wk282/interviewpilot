from __future__ import annotations

from pathlib import Path

from .contracts import TextBlock


class PaddleOCRBackend:
    """Optional PaddleOCR 2.x adapter used only by the isolated experiment."""

    name = "PADDLE_OCR_2X"

    def __init__(self, *, lang: str = "ch", render_scale: float = 2.5) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise RuntimeError("Install requirements-ocr.txt to use PaddleOCR") from error
        self.engine = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        self.render_scale = render_scale

    def recognize_page(self, document_path: Path, page_index: int) -> list[TextBlock]:
        try:
            import cv2
            import fitz
            import numpy as np
        except ImportError as error:
            raise RuntimeError("OCR rendering dependencies are missing") from error

        with fitz.open(document_path) as document:
            page = document.load_page(page_index)
            matrix = fitz.Matrix(self.render_scale, self.render_scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pixmap.tobytes("png")

        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Failed to render the PDF page for OCR")
        raw_result = self.engine.ocr(image, cls=True)
        page_result = raw_result[0] if raw_result else []
        blocks: list[TextBlock] = []
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
                TextBlock(
                    block_type="paragraph",
                    text=text,
                    bbox=(min(x_values), min(y_values), max(x_values), max(y_values)),
                    source="OCR",
                    confidence=confidence,
                    metadata={"coordinate_space": "rendered_pixels"},
                )
            )
        return blocks

