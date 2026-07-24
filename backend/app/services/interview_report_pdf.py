from __future__ import annotations

import unicodedata
from datetime import datetime
from io import BytesIO
from typing import Any, Iterable

import fitz

from app.db.models.interview import (
    InterviewEvaluation,
    InterviewPlanRevision,
    InterviewQualityAudit,
    InterviewTurnCritique,
)


DIMENSION_LABELS = {
    "technical_depth": "技术深度",
    "project_authenticity": "项目可信度",
    "problem_solving": "问题解决",
    "system_design": "系统设计",
    "communication": "表达沟通",
}

RECOMMENDATION_LABELS = {
    "STRONG_HIRE": "强烈推荐",
    "HIRE": "推荐",
    "HOLD": "待定",
    "NO_HIRE": "不推荐",
    "NOT_APPLICABLE": "模拟面试",
}

RECOMMENDATION_COLORS = {
    "STRONG_HIRE": (0.04, 0.45, 0.33),
    "HIRE": (0.04, 0.45, 0.33),
    "HOLD": (0.72, 0.43, 0.08),
    "NO_HIRE": (0.72, 0.18, 0.20),
    "NOT_APPLICABLE": (0.19, 0.36, 0.62),
}

ACTION_LABELS = {
    "FOLLOW_UP": "继续追问",
    "INCREASE_DIFFICULTY": "提高难度",
    "DECREASE_DIFFICULTY": "降低难度",
    "SWITCH_TOPIC": "切换能力点",
    "END_INTERVIEW": "结束面试",
    "FINISH": "结束面试",
}

INK = (0.12, 0.14, 0.18)
MUTED = (0.42, 0.45, 0.49)
BRAND = (0.04, 0.29, 0.24)
BRAND_SOFT = (0.91, 0.96, 0.94)
GREEN = (0.04, 0.45, 0.33)
GREEN_SOFT = (0.92, 0.97, 0.95)
RED = (0.72, 0.18, 0.20)
RED_SOFT = (0.99, 0.94, 0.94)
AMBER = (0.72, 0.43, 0.08)
BLUE = (0.19, 0.36, 0.62)
LINE = (0.84, 0.86, 0.88)
PANEL = (0.97, 0.98, 0.98)
WHITE = (1.0, 1.0, 1.0)


def _display_width(character: str) -> int:
    return 2 if unicodedata.east_asian_width(character) in {"W", "F", "A"} else 1


def _wrap_text(value: Any, max_width: int) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return [""]
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current: list[str] = []
        width = 0
        for character in paragraph:
            character_width = _display_width(character)
            if current and width + character_width > max_width:
                lines.append("".join(current))
                current = []
                width = 0
            current.append(character)
            width += character_width
        lines.append("".join(current))
    return lines


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _format_gate_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "完整" if value else "不完整"
    if key == "score_consistency":
        return f"{_safe_float(value):.1f} 分"
    return f"{_safe_float(value) * 100:.0f}%"


def _format_gate_threshold(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "必须完整"
    operator = "≤" if key in {"fallback_turn_rate", "question_repetition", "score_consistency"} else "≥"
    if key == "score_consistency":
        return f"{operator} {_safe_float(value):.0f} 分"
    return f"{operator} {_safe_float(value) * 100:.0f}%"


class PdfWriter:
    page_width = 595.0
    page_height = 842.0
    margin_x = 44.0
    top = 66.0
    bottom = 52.0

    def __init__(self) -> None:
        self.document = fitz.open()
        self.page: fitz.Page | None = None
        self.y = 0.0
        self._new_page()

    @property
    def content_width(self) -> float:
        return self.page_width - self.margin_x * 2

    @property
    def available_bottom(self) -> float:
        return self.page_height - self.bottom

    def _new_page(self) -> None:
        self.page = self.document.new_page(width=self.page_width, height=self.page_height)
        self.y = self.top

    def _ensure_space(self, height: float) -> None:
        if self.y + height > self.available_bottom:
            self._new_page()

    def _lines(self, value: Any, width: float, font_size: float) -> list[str]:
        display_units = max(8, int(width / font_size * 1.9))
        return _wrap_text(value, display_units)

    def _draw_lines_at(
        self,
        *,
        x: float,
        top: float,
        lines: list[str],
        font_size: float,
        color: tuple[float, float, float] = INK,
        line_height: float | None = None,
    ) -> float:
        assert self.page is not None
        height = line_height or font_size * 1.45
        cursor = top
        for line in lines:
            self.page.insert_text(
                (x, cursor + font_size),
                line,
                fontname="china-s",
                fontsize=font_size,
                color=color,
            )
            cursor += height
        return cursor

    def text(
        self,
        value: Any,
        *,
        font_size: float = 10.0,
        color: tuple[float, float, float] = INK,
        indent: float = 0,
        gap_after: float = 4,
        width: float | None = None,
    ) -> None:
        text_width = width or self.content_width - indent
        lines = self._lines(value, text_width, font_size)
        line_height = font_size * 1.5
        for line in lines:
            self._ensure_space(line_height)
            self._draw_lines_at(
                x=self.margin_x + indent,
                top=self.y,
                lines=[line],
                font_size=font_size,
                color=color,
                line_height=line_height,
            )
            self.y += line_height
        self.y += gap_after

    def cover(
        self,
        *,
        candidate_name: str,
        job_title: str,
        completed_at: datetime | None,
        model_name: str | None,
    ) -> None:
        assert self.page is not None
        self.page.draw_rect(
            fitz.Rect(0, 0, self.page_width, 178),
            color=BRAND,
            fill=BRAND,
            width=0,
        )
        self.page.insert_text(
            (self.margin_x, 35),
            "INTERVIEWPILOT",
            fontname="helv",
            fontsize=9,
            color=(0.72, 0.89, 0.84),
        )
        self.page.insert_text(
            (self.margin_x, 75),
            "面试评估报告",
            fontname="china-s",
            fontsize=25,
            color=WHITE,
        )
        candidate_lines = self._lines(candidate_name, 300, 14)
        self._draw_lines_at(
            x=self.margin_x,
            top=96,
            lines=candidate_lines[:2],
            font_size=14,
            color=WHITE,
            line_height=20,
        )
        self._draw_lines_at(
            x=342,
            top=96,
            lines=self._lines(job_title, 209, 10)[:2],
            font_size=10,
            color=(0.86, 0.94, 0.92),
            line_height=16,
        )
        self.page.insert_text(
            (self.margin_x, 158),
            f"完成时间  {_format_datetime(completed_at)}",
            fontname="china-s",
            fontsize=8.5,
            color=(0.72, 0.89, 0.84),
        )
        self.page.insert_text(
            (342, 158),
            f"评估模型  {model_name or '-'}",
            fontname="china-s",
            fontsize=8.5,
            color=(0.72, 0.89, 0.84),
        )
        self.y = 202

    def heading(self, text: str, subtitle: str | None = None) -> None:
        height = 36 if subtitle else 28
        self._ensure_space(height)
        assert self.page is not None
        self.page.draw_rect(
            fitz.Rect(self.margin_x, self.y + 2, self.margin_x + 3, self.y + 20),
            color=BRAND,
            fill=BRAND,
            width=0,
        )
        self.page.insert_text(
            (self.margin_x + 11, self.y + 15),
            text,
            fontname="china-s",
            fontsize=13,
            color=INK,
        )
        if subtitle:
            self.page.insert_text(
                (self.margin_x + 11, self.y + 31),
                subtitle,
                fontname="china-s",
                fontsize=8.5,
                color=MUTED,
            )
        self.y += height

    def score_overview(
        self,
        *,
        overall_score: float | None,
        recommendation_code: str,
        dimensions: dict,
    ) -> None:
        height = 160.0
        self._ensure_space(height)
        assert self.page is not None
        left_width = 136.0
        gap = 12.0
        right_x = self.margin_x + left_width + gap
        right_width = self.content_width - left_width - gap
        top = self.y
        self.page.draw_rect(
            fitz.Rect(self.margin_x, top, self.margin_x + left_width, top + height),
            color=LINE,
            fill=BRAND_SOFT,
            width=0.7,
        )
        self.page.draw_rect(
            fitz.Rect(right_x, top, right_x + right_width, top + height),
            color=LINE,
            fill=WHITE,
            width=0.7,
        )
        self.page.insert_text(
            (self.margin_x + 16, top + 25),
            "综合得分",
            fontname="china-s",
            fontsize=9,
            color=MUTED,
        )
        score_text = f"{overall_score:.1f}" if overall_score is not None else "-"
        self.page.insert_text(
            (self.margin_x + 16, top + 76),
            score_text,
            fontname="helv",
            fontsize=39,
            color=BRAND,
        )
        self.page.insert_text(
            (self.margin_x + 92, top + 76),
            "/ 100",
            fontname="helv",
            fontsize=9,
            color=MUTED,
        )
        recommendation = RECOMMENDATION_LABELS.get(
            recommendation_code, recommendation_code or "-"
        )
        recommendation_color = RECOMMENDATION_COLORS.get(recommendation_code, BLUE)
        self.page.draw_rect(
            fitz.Rect(
                self.margin_x + 16,
                top + 105,
                self.margin_x + left_width - 16,
                top + 134,
            ),
            color=recommendation_color,
            fill=WHITE,
            width=0.8,
        )
        recommendation_lines = self._lines(recommendation, left_width - 44, 9)
        self._draw_lines_at(
            x=self.margin_x + 27,
            top=top + 111,
            lines=recommendation_lines[:1],
            font_size=9,
            color=recommendation_color,
        )

        self.page.insert_text(
            (right_x + 16, top + 23),
            "能力维度",
            fontname="china-s",
            fontsize=10,
            color=INK,
        )
        bar_x = right_x + 100
        bar_width = right_width - 150
        for index, (key, label) in enumerate(DIMENSION_LABELS.items()):
            row_y = top + 42 + index * 22
            score = max(0.0, min(100.0, _safe_float(dimensions.get(key))))
            self.page.insert_text(
                (right_x + 16, row_y + 8),
                label,
                fontname="china-s",
                fontsize=8.5,
                color=MUTED,
            )
            self.page.draw_rect(
                fitz.Rect(bar_x, row_y, bar_x + bar_width, row_y + 8),
                color=(0.90, 0.91, 0.92),
                fill=(0.90, 0.91, 0.92),
                width=0,
            )
            fill_color = GREEN if score >= 70 else AMBER if score >= 50 else RED
            if score > 0:
                self.page.draw_rect(
                    fitz.Rect(bar_x, row_y, bar_x + bar_width * score / 100, row_y + 8),
                    color=fill_color,
                    fill=fill_color,
                    width=0,
                )
            self.page.insert_text(
                (right_x + right_width - 35, row_y + 8),
                f"{score:.0f}",
                fontname="helv",
                fontsize=8.5,
                color=INK,
            )
        self.y += height + 18

    def _list_lines(self, items: Iterable[Any], width: float) -> list[str]:
        values = [str(item).strip() for item in items if str(item).strip()]
        if not values:
            return ["暂无"]
        lines: list[str] = []
        for value in values:
            wrapped = self._lines(f"• {value}", width, 9.2)
            lines.extend(wrapped)
            lines.append("")
        return lines[:-1]

    def two_column_lists(
        self,
        *,
        left_title: str,
        left_items: Iterable[Any],
        right_title: str,
        right_items: Iterable[Any],
    ) -> None:
        gap = 12.0
        column_width = (self.content_width - gap) / 2
        body_width = column_width - 28
        left_lines = self._list_lines(left_items, body_width)
        right_lines = self._list_lines(right_items, body_width)
        line_height = 13.5
        height = 44 + max(len(left_lines), len(right_lines)) * line_height
        if height > 570:
            self.heading(left_title)
            for item in left_items:
                self.text(f"• {item}", indent=8)
            self.heading(right_title)
            for item in right_items:
                self.text(f"• {item}", indent=8)
            return
        self._ensure_space(height)
        assert self.page is not None
        top = self.y
        left_x = self.margin_x
        right_x = left_x + column_width + gap
        for x, title, lines, fill, accent in (
            (left_x, left_title, left_lines, GREEN_SOFT, GREEN),
            (right_x, right_title, right_lines, RED_SOFT, RED),
        ):
            self.page.draw_rect(
                fitz.Rect(x, top, x + column_width, top + height),
                color=LINE,
                fill=fill,
                width=0.6,
            )
            self.page.insert_text(
                (x + 14, top + 23),
                title,
                fontname="china-s",
                fontsize=10.5,
                color=accent,
            )
            self._draw_lines_at(
                x=x + 14,
                top=top + 35,
                lines=lines,
                font_size=9.2,
                color=INK if lines != ["暂无"] else MUTED,
                line_height=line_height,
            )
        self.y += height + 18

    def paragraph_panel(self, text: Any) -> None:
        lines = self._lines(text or "暂无", self.content_width - 30, 9.5)
        height = 26 + len(lines) * 14.5
        if height > 620:
            self.text(text or "暂无", indent=8)
            return
        self._ensure_space(height)
        assert self.page is not None
        top = self.y
        self.page.draw_rect(
            fitz.Rect(self.margin_x, top, self.margin_x + self.content_width, top + height),
            color=LINE,
            fill=PANEL,
            width=0.6,
        )
        self._draw_lines_at(
            x=self.margin_x + 15,
            top=top + 13,
            lines=lines,
            font_size=9.5,
            line_height=14.5,
        )
        self.y += height + 16

    def evidence_card(self, index: int, item: dict) -> None:
        dimension = DIMENSION_LABELS.get(
            str(item.get("dimension") or ""), str(item.get("dimension") or "未分类")
        )
        score = item.get("score", "-")
        sections = [
            ("问题", item.get("question", "-")),
            ("回答摘录", item.get("answer_excerpt", "-")),
            ("评估判断", item.get("finding", "-")),
        ]
        wrapped = [
            (label, self._lines(value, self.content_width - 48, 9.0))
            for label, value in sections
        ]
        height = 48 + sum(18 + len(lines) * 13.5 for _, lines in wrapped)
        if height > 650:
            self._ensure_space(40)
            self.text(f"证据 {index} · {dimension} · {score} 分", color=BRAND)
            for label, value in sections:
                self.text(label, font_size=8.5, color=MUTED, gap_after=1)
                self.text(value, indent=8, gap_after=8)
            return
        self._ensure_space(height)
        assert self.page is not None
        top = self.y
        self.page.draw_rect(
            fitz.Rect(self.margin_x, top, self.margin_x + self.content_width, top + height),
            color=LINE,
            fill=WHITE,
            width=0.7,
        )
        self.page.draw_rect(
            fitz.Rect(self.margin_x, top, self.margin_x + 4, top + height),
            color=BRAND,
            fill=BRAND,
            width=0,
        )
        self.page.insert_text(
            (self.margin_x + 16, top + 23),
            f"证据 {index}  ·  {dimension}  ·  {score} 分",
            fontname="china-s",
            fontsize=10.2,
            color=BRAND,
        )
        cursor = top + 39
        for label, lines in wrapped:
            self.page.insert_text(
                (self.margin_x + 16, cursor + 9),
                label,
                fontname="china-s",
                fontsize=8.3,
                color=MUTED,
            )
            cursor += 16
            cursor = self._draw_lines_at(
                x=self.margin_x + 24,
                top=cursor,
                lines=lines,
                font_size=9.0,
                line_height=13.5,
            )
            cursor += 5
        self.y += height + 12

    def timeline_item(
        self,
        *,
        title: str,
        body: Any,
        detail: str | None = None,
        accent: tuple[float, float, float] = BRAND,
    ) -> None:
        body_lines = self._lines(body or "暂无", self.content_width - 54, 9.2)
        detail_lines = self._lines(detail, self.content_width - 54, 8.3) if detail else []
        height = 32 + len(body_lines) * 13.5 + len(detail_lines) * 12
        self._ensure_space(height)
        assert self.page is not None
        top = self.y
        self.page.draw_line(
            (self.margin_x + 8, top),
            (self.margin_x + 8, top + height),
            color=LINE,
            width=1,
        )
        self.page.draw_rect(
            fitz.Rect(self.margin_x + 4, top + 5, self.margin_x + 12, top + 13),
            color=accent,
            fill=accent,
            width=0,
        )
        self.page.insert_text(
            (self.margin_x + 25, top + 14),
            title,
            fontname="china-s",
            fontsize=9.8,
            color=accent,
        )
        cursor = self._draw_lines_at(
            x=self.margin_x + 25,
            top=top + 22,
            lines=body_lines,
            font_size=9.2,
            line_height=13.5,
        )
        if detail_lines:
            self._draw_lines_at(
                x=self.margin_x + 25,
                top=cursor + 3,
                lines=detail_lines,
                font_size=8.3,
                color=MUTED,
                line_height=12,
            )
        self.y += height + 5

    def quality_table(self, quality_audit: InterviewQualityAudit) -> None:
        assert self.page is not None
        status_color = GREEN if quality_audit.passed else RED
        self._ensure_space(52)
        self.page.draw_rect(
            fitz.Rect(self.margin_x, self.y, self.margin_x + self.content_width, self.y + 38),
            color=status_color,
            fill=GREEN_SOFT if quality_audit.passed else RED_SOFT,
            width=0.7,
        )
        self.page.insert_text(
            (self.margin_x + 14, self.y + 24),
            f"质量门禁：{'通过' if quality_audit.passed else '未通过'}",
            fontname="china-s",
            fontsize=11,
            color=status_color,
        )
        self.page.insert_text(
            (self.margin_x + 365, self.y + 23),
            quality_audit.audit_version,
            fontname="helv",
            fontsize=8,
            color=MUTED,
        )
        self.y += 52

        columns = [self.margin_x, self.margin_x + 238, self.margin_x + 326, self.margin_x + 424]
        widths = [238, 88, 98, 83]

        def draw_header() -> None:
            assert self.page is not None
            self.page.draw_rect(
                fitz.Rect(self.margin_x, self.y, self.margin_x + self.content_width, self.y + 28),
                color=BRAND,
                fill=BRAND,
                width=0,
            )
            for x, label in zip(columns, ("指标", "实际值", "门禁", "结果")):
                self.page.insert_text(
                    (x + 9, self.y + 18),
                    label,
                    fontname="china-s",
                    fontsize=8.5,
                    color=WHITE,
                )
            self.y += 28

        draw_header()
        for index, gate in enumerate(quality_audit.quality_gates or []):
            if self.y + 30 > self.available_bottom:
                self._new_page()
                self.heading("业务质量审计（续）")
                draw_header()
            assert self.page is not None
            fill = WHITE if index % 2 == 0 else PANEL
            self.page.draw_rect(
                fitz.Rect(self.margin_x, self.y, self.margin_x + self.content_width, self.y + 30),
                color=LINE,
                fill=fill,
                width=0.4,
            )
            key = str(gate.get("key") or "")
            values = (
                str(gate.get("label") or key),
                _format_gate_value(key, gate.get("value")),
                _format_gate_threshold(key, gate.get("threshold")),
                "通过" if gate.get("passed") else "未通过",
            )
            for column_index, (x, width, value) in enumerate(zip(columns, widths, values)):
                cell_color = (
                    GREEN if gate.get("passed") else RED
                ) if column_index == 3 else INK
                cell_lines = self._lines(value, width - 16, 8.2)
                self._draw_lines_at(
                    x=x + 8,
                    top=self.y + 8,
                    lines=cell_lines[:1],
                    font_size=8.2,
                    color=cell_color,
                )
            self.y += 30
        self.y += 12
        if quality_audit.warnings:
            self.text("需要关注", font_size=9.5, color=RED, gap_after=3)
            for warning in quality_audit.warnings:
                self.text(f"• {warning}", indent=8, font_size=9.0, gap_after=2)

    def empty(self, text: str = "暂无数据") -> None:
        self.text(text, color=MUTED, indent=8, gap_after=12)

    def _add_page_furniture(self) -> None:
        total = len(self.document)
        generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        for index, page in enumerate(self.document):
            if index > 0:
                page.insert_text(
                    (self.margin_x, 32),
                    "INTERVIEWPILOT  /  面试评估报告",
                    fontname="china-s",
                    fontsize=7.5,
                    color=MUTED,
                )
                page.draw_line(
                    (self.margin_x, 43),
                    (self.page_width - self.margin_x, 43),
                    color=LINE,
                    width=0.5,
                )
            page.draw_line(
                (self.margin_x, self.page_height - 36),
                (self.page_width - self.margin_x, self.page_height - 36),
                color=LINE,
                width=0.5,
            )
            page.insert_text(
                (self.margin_x, self.page_height - 20),
                f"生成时间 {generated_at}  ·  仅限授权招聘评估使用",
                fontname="china-s",
                fontsize=7,
                color=MUTED,
            )
            page.insert_text(
                (self.page_width - self.margin_x - 48, self.page_height - 20),
                f"{index + 1} / {total}",
                fontname="helv",
                fontsize=7,
                color=MUTED,
            )

    def bytes(self) -> bytes:
        self._add_page_furniture()
        output = BytesIO()
        self.document.save(output, garbage=4, deflate=True)
        self.document.close()
        return output.getvalue()


def build_interview_report_pdf(
    *,
    evaluation: InterviewEvaluation,
    candidate_name: str,
    job_title: str,
    completed_at: datetime | None,
    critiques: list[InterviewTurnCritique],
    revisions: list[InterviewPlanRevision],
    quality_audit: InterviewQualityAudit | None,
) -> bytes:
    writer = PdfWriter()
    writer.cover(
        candidate_name=candidate_name,
        job_title=job_title,
        completed_at=completed_at,
        model_name=evaluation.model_name,
    )
    overall_score = (
        _safe_float(evaluation.overall_score)
        if evaluation.overall_score is not None
        else None
    )
    writer.score_overview(
        overall_score=overall_score,
        recommendation_code=evaluation.recommendation or "",
        dimensions=dict(evaluation.dimension_scores or {}),
    )

    writer.heading("能力结论", "从优势与风险两个方向概括本次面试表现")
    writer.two_column_lists(
        left_title="主要优势",
        left_items=evaluation.strengths or [],
        right_title="待提升项",
        right_items=evaluation.weaknesses or [],
    )

    writer.heading("综合评价")
    writer.paragraph_panel(evaluation.report_text or "暂无")

    writer.heading("回答证据", "所有引用均来自候选人的实际回答")
    evidence_items = [item for item in (evaluation.evidence or []) if isinstance(item, dict)]
    if not evidence_items:
        writer.empty()
    for index, item in enumerate(evidence_items, start=1):
        writer.evidence_card(index, item)

    writer.heading("逐轮 Critic 决策", "展示每轮评分、动作与决策依据")
    if not critiques:
        writer.empty()
    for index, critique in enumerate(critiques, start=1):
        action = ACTION_LABELS.get(critique.next_action, critique.next_action)
        source = "模型" if critique.decision_source == "MODEL" else "规则降级"
        writer.timeline_item(
            title=f"第 {index} 轮  ·  {float(critique.score):.0f} 分  ·  {action}",
            body=critique.reason,
            detail=f"决策来源：{source}  ·  置信度：{float(critique.confidence) * 100:.0f}%",
            accent=GREEN if critique.decision_source == "MODEL" else AMBER,
        )

    writer.heading("动态计划修订", "保留计划版本、调整动作和剩余能力预算")
    if not revisions:
        writer.empty()
    for revision in revisions:
        action = ACTION_LABELS.get(revision.action, revision.action)
        target = revision.target_competency or "未指定能力点"
        budget_text = "；".join(
            f"{competency} {count}题"
            for competency, count in (revision.competency_budget or {}).items()
        )
        detail = f"剩余题目预算：{revision.remaining_question_budget}"
        if budget_text:
            detail += f"  ·  能力预算：{budget_text}"
        writer.timeline_item(
            title=f"计划 v{revision.version}  ·  {action}  ·  {target}",
            body=revision.rationale,
            detail=detail,
            accent=BLUE,
        )

    if quality_audit is not None:
        writer.heading("业务质量审计", "对面试过程、Agent决策和报告证据执行质量门禁")
        writer.quality_table(quality_audit)

    return writer.bytes()
