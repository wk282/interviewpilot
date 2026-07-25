from __future__ import annotations

import html
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import Any

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

RECOMMENDATION_CLASSES = {
    "STRONG_HIRE": "badge-green",
    "HIRE": "badge-green",
    "HOLD": "badge-amber",
    "NO_HIRE": "badge-red",
    "NOT_APPLICABLE": "badge-blue",
}

ACTION_LABELS = {
    "FOLLOW_UP": "继续追问",
    "INCREASE_DIFFICULTY": "提高难度",
    "DECREASE_DIFFICULTY": "降低难度",
    "SWITCH_TOPIC": "切换能力点",
    "END_INTERVIEW": "结束面试",
    "FINISH": "结束面试",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _esc(value: Any) -> str:
    return html.escape(str(value or "").strip())


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
    overall_score = (
        _safe_float(evaluation.overall_score)
        if evaluation.overall_score is not None
        else None
    )
    score_display = f"{overall_score:.1f}" if overall_score is not None else "-"
    rec_code = evaluation.recommendation or ""
    rec_label = RECOMMENDATION_LABELS.get(rec_code, rec_code or "-")
    rec_class = RECOMMENDATION_CLASSES.get(rec_code, "badge-blue")
    dimensions = dict(evaluation.dimension_scores or {})

    strengths_items = evaluation.strengths or []
    weaknesses_items = evaluation.weaknesses or []

    strengths_html = (
        "".join(f"<li>{_esc(item)}</li>" for item in strengths_items)
        if strengths_items
        else "<li>暂无</li>"
    )
    weaknesses_html = (
        "".join(f"<li>{_esc(item)}</li>" for item in weaknesses_items)
        if weaknesses_items
        else "<li>暂无</li>"
    )

    dim_bars_html = ""
    for key, label in DIMENSION_LABELS.items():
        score = max(0.0, min(100.0, _safe_float(dimensions.get(key))))
        bar_color = (
            "#047857" if score >= 70 else "#b45309" if score >= 50 else "#b91c1c"
        )
        dim_bars_html += f"""
        <div class="dim-row">
          <span class="dim-label">{_esc(label)}</span>
          <div class="dim-track">
            <div class="dim-fill" style="width: {score}%; background-color: {bar_color};"></div>
          </div>
          <span class="dim-score">{score:.0f}</span>
        </div>
        """

    evidence_items = [
        item for item in (evaluation.evidence or []) if isinstance(item, dict)
    ]
    evidence_html = ""
    if not evidence_items:
        evidence_html = '<p class="muted">暂无证据关联</p>'
    else:
        for idx, item in enumerate(evidence_items, start=1):
            dim_label = DIMENSION_LABELS.get(
                str(item.get("dimension") or ""),
                str(item.get("dimension") or "未分类"),
            )
            score_val = item.get("score", "-")
            evidence_html += f"""
            <div class="evidence-card">
              <div class="evidence-header">
                <strong>证据 {idx}</strong> · <span class="tag">{_esc(dim_label)}</span> · <span class="badge-score">{score_val} 分</span>
              </div>
              <div class="evidence-item">
                <div class="item-title">问题</div>
                <div class="item-body">{_esc(item.get("question", "-"))}</div>
              </div>
              <div class="evidence-item">
                <div class="item-title">回答摘录</div>
                <div class="item-body excerpt">{_esc(item.get("answer_excerpt", "-"))}</div>
              </div>
              <div class="evidence-item">
                <div class="item-title">评估判断</div>
                <div class="item-body finding">{_esc(item.get("finding", "-"))}</div>
              </div>
            </div>
            """

    critiques_html = ""
    if not critiques:
        critiques_html = '<p class="muted">暂无逐轮决策数据</p>'
    else:
        for idx, c in enumerate(critiques, start=1):
            action = ACTION_LABELS.get(c.next_action, c.next_action)
            source = "模型" if c.decision_source == "MODEL" else "规则降级"
            conf = f"{_safe_float(c.confidence) * 100:.0f}%"
            score_val = f"{_safe_float(c.score):.0f}"
            critiques_html += f"""
            <div class="timeline-item">
              <div class="timeline-header">
                <strong>第 {idx} 轮</strong> · <span class="badge-score">{score_val} 分</span> · <span class="tag">{_esc(action)}</span>
              </div>
              <div class="timeline-body">{_esc(c.reason)}</div>
              <div class="timeline-meta">决策来源：{source} · 置信度：{conf}</div>
            </div>
            """

    revisions_html = ""
    if not revisions:
        revisions_html = '<p class="muted">暂无计划修订记录</p>'
    else:
        for r in revisions:
            action = ACTION_LABELS.get(r.action, r.action)
            target = r.target_competency or "未指定能力点"
            budget_items = [
                f"{comp} {cnt}题"
                for comp, cnt in (r.competency_budget or {}).items()
            ]
            budget_str = f" · 能力预算：{'；'.join(budget_items)}" if budget_items else ""
            revisions_html += f"""
            <div class="timeline-item blue">
              <div class="timeline-header">
                <strong>计划 v{r.version}</strong> · <span class="tag">{_esc(action)}</span> · <span>{_esc(target)}</span>
              </div>
              <div class="timeline-body">{_esc(r.rationale)}</div>
              <div class="timeline-meta">剩余题目预算：{r.remaining_question_budget}{_esc(budget_str)}</div>
            </div>
            """

    audit_html = ""
    if quality_audit is not None:
        passed = quality_audit.passed
        pass_class = "audit-pass" if passed else "audit-fail"
        pass_text = "通过" if passed else "未通过"
        gates_html = ""
        for g in quality_audit.quality_gates or []:
            key = str(g.get("key") or "")
            label = str(g.get("label") or key)
            val_raw = g.get("value")
            val_str = (
                ("完整" if val_raw else "不完整")
                if isinstance(val_raw, bool)
                else (
                    f"{_safe_float(val_raw):.1f} 分"
                    if key == "score_consistency"
                    else f"{_safe_float(val_raw) * 100:.0f}%"
                )
            )
            thr_raw = g.get("threshold")
            op = (
                "≤"
                if key
                in {
                    "fallback_turn_rate",
                    "question_repetition",
                    "score_consistency",
                }
                else "≥"
            )
            thr_str = (
                "必须完整"
                if isinstance(thr_raw, bool)
                else (
                    f"{op} {_safe_float(thr_raw):.0f} 分"
                    if key == "score_consistency"
                    else f"{op} {_safe_float(thr_raw) * 100:.0f}%"
                )
            )
            res_str = "通过" if g.get("passed") else "未通过"
            res_class = "pass" if g.get("passed") else "fail"
            gates_html += f"""
            <tr>
              <td>{_esc(label)}</td>
              <td>{_esc(val_str)}</td>
              <td>{_esc(thr_str)}</td>
              <td class="{res_class}">{res_str}</td>
            </tr>
            """
        warnings_html = ""
        if quality_audit.warnings:
            warn_items = "".join(
                f"<li>{_esc(w)}</li>" for w in quality_audit.warnings
            )
            warnings_html = f'<div class="audit-warnings"><strong>需要关注：</strong><ul>{warn_items}</ul></div>'

        audit_html = f"""
        <div class="section-title">业务质量审计</div>
        <div class="audit-banner {pass_class}">
          <strong>质量门禁：{pass_text}</strong>
          <span class="audit-version">{_esc(quality_audit.audit_version)}</span>
        </div>
        <table class="audit-table">
          <thead>
            <tr><th>指标</th><th>实际值</th><th>门禁</th><th>结果</th></tr>
          </thead>
          <tbody>
            {gates_html}
          </tbody>
        </table>
        {warnings_html}
        """

    full_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: sans-serif;
    color: #1e293b;
    margin: 0;
    padding: 0;
    font-size: 9.5pt;
    line-height: 1.5;
  }}
  .header {{
    background-color: #0b4a3e;
    color: #ffffff;
    padding: 20px 24px;
    border-radius: 8px;
    margin-bottom: 20px;
  }}
  .header-brand {{
    font-size: 8pt;
    letter-spacing: 1px;
    color: #a7f3d0;
    font-weight: 600;
  }}
  .header-title {{
    font-size: 22pt;
    font-weight: bold;
    margin: 4px 0 8px 0;
  }}
  .header-meta {{
    font-size: 10pt;
    color: #e2e8f0;
  }}
  .header-info {{
    font-size: 8.5pt;
    color: #a7f3d0;
    margin-top: 12px;
  }}
  .overview-grid {{
    display: table;
    width: 100%;
    margin-bottom: 20px;
  }}
  .score-box {{
    display: table-cell;
    width: 32%;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 16px;
    vertical-align: top;
    text-align: center;
  }}
  .score-val {{
    font-size: 32pt;
    font-weight: bold;
    color: #0b4a3e;
    line-height: 1;
  }}
  .score-max {{
    font-size: 9pt;
    color: #64748b;
  }}
  .badge-rec {{
    display: inline-block;
    margin-top: 12px;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 9pt;
    font-weight: 600;
  }}
  .badge-green {{ background: #dcfce7; color: #15803d; border: 1px solid #86efac; }}
  .badge-amber {{ background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }}
  .badge-red {{ background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }}
  .badge-blue {{ background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }}
  
  .dim-box {{
    display: table-cell;
    width: 65%;
    padding-left: 3%;
    vertical-align: top;
  }}
  .dim-row {{
    margin-bottom: 8px;
  }}
  .dim-label {{
    display: inline-block;
    width: 80px;
    font-size: 8.5pt;
    color: #475569;
  }}
  .dim-track {{
    display: inline-block;
    width: 180px;
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
    vertical-align: middle;
  }}
  .dim-fill {{
    height: 100%;
    border-radius: 4px;
  }}
  .dim-score {{
    display: inline-block;
    margin-left: 8px;
    font-size: 8.5pt;
    font-weight: 600;
    color: #1e293b;
  }}

  .section-title {{
    font-size: 13pt;
    font-weight: bold;
    color: #0b4a3e;
    border-left: 4px solid #0b4a3e;
    padding-left: 8px;
    margin: 22px 0 12px 0;
  }}
  .two-col {{
    display: table;
    width: 100%;
    margin-bottom: 20px;
  }}
  .col-card {{
    display: table-cell;
    width: 48.5%;
    vertical-align: top;
    padding: 14px;
    border-radius: 8px;
  }}
  .col-card.green {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
  .col-card.red {{ background: #fef2f2; border: 1px solid #fecaca; }}
  .col-card h4 {{ margin: 0 0 8px 0; font-size: 10.5pt; }}
  .col-card.green h4 {{ color: #15803d; }}
  .col-card.red h4 {{ color: #b91c1c; }}
  .col-card ul {{ margin: 0; padding-left: 16px; color: #334155; }}
  .col-card li {{ margin-bottom: 4px; }}

  .panel {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 20px;
    color: #334155;
    white-space: pre-wrap;
  }}

  .evidence-card {{
    border: 1px solid #cbd5e1;
    border-left: 4px solid #0b4a3e;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 12px;
    background: #ffffff;
  }}
  .evidence-header {{
    font-size: 9.5pt;
    color: #0b4a3e;
    margin-bottom: 8px;
  }}
  .badge-score {{
    background: #e0f2fe;
    color: #0369a1;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 8pt;
    font-weight: 600;
  }}
  .tag {{
    background: #f1f5f9;
    color: #475569;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 8pt;
  }}
  .evidence-item {{
    margin-bottom: 6px;
  }}
  .item-title {{
    font-size: 8pt;
    color: #64748b;
    font-weight: 600;
  }}
  .item-body {{
    font-size: 9pt;
    color: #1e293b;
  }}
  .item-body.excerpt {{
    color: #334155;
    font-style: italic;
    background: #f8fafc;
    padding: 6px;
    border-radius: 4px;
  }}

  .timeline-item {{
    border-left: 2px solid #cbd5e1;
    padding-left: 12px;
    margin-left: 6px;
    margin-bottom: 12px;
  }}
  .timeline-item.blue {{ border-left-color: #3b82f6; }}
  .timeline-header {{
    font-size: 9pt;
    color: #0b4a3e;
    margin-bottom: 4px;
  }}
  .timeline-body {{
    font-size: 9pt;
    color: #334155;
  }}
  .timeline-meta {{
    font-size: 8pt;
    color: #64748b;
    margin-top: 4px;
  }}

  .audit-banner {{
    padding: 10px 14px;
    border-radius: 6px;
    margin-bottom: 12px;
    font-size: 10pt;
  }}
  .audit-pass {{ background: #dcfce7; color: #15803d; border: 1px solid #86efac; }}
  .audit-fail {{ background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }}
  .audit-version {{ float: right; font-size: 8pt; color: #64748b; }}

  .audit-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
  }}
  .audit-table th {{
    background: #0b4a3e;
    color: #ffffff;
    padding: 6px 10px;
    text-align: left;
  }}
  .audit-table td {{
    padding: 6px 10px;
    border-bottom: 1px solid #e2e8f0;
  }}
  .audit-table td.pass {{ color: #166534; font-weight: 600; }}
  .audit-table td.fail {{ color: #dc2626; font-weight: 600; }}
  .audit-warnings {{
    margin-top: 10px;
    color: #dc2626;
    font-size: 8.5pt;
  }}
  .muted {{ color: #64748b; font-size: 9pt; }}
</style>
</head>
<body>
  <div class="header">
    <div class="header-brand">INTERVIEWPILOT</div>
    <div class="header-title">面试评估报告</div>
    <div class="header-meta">{_esc(candidate_name)} · {_esc(job_title)}</div>
    <div class="header-info">完成时间：{_format_datetime(completed_at)} &nbsp;|&nbsp; 评估模型：{_esc(evaluation.model_name or '-')}</div>
  </div>

  <div class="overview-grid">
    <div class="score-box">
      <div style="font-size: 8.5pt; color: #64748b; margin-bottom: 4px;">综合得分</div>
      <div class="score-val">{score_display} <span class="score-max">/ 100</span></div>
      <div class="badge-rec {rec_class}">{_esc(rec_label)}</div>
    </div>
    <div class="dim-box">
      <div style="font-weight: 600; font-size: 9.5pt; margin-bottom: 8px;">能力维度评估</div>
      {dim_bars_html}
    </div>
  </div>

  <div class="section-title">能力结论</div>
  <div class="two-col">
    <div class="col-card green">
      <h4>主要优势</h4>
      <ul>{strengths_html}</ul>
    </div>
    <div style="display: table-cell; width: 3%;"></div>
    <div class="col-card red">
      <h4>待提升项</h4>
      <ul>{weaknesses_html}</ul>
    </div>
  </div>

  <div class="section-title">综合评价</div>
  <div class="panel">{_esc(evaluation.report_text or "暂无")}</div>

  <div class="section-title">回答证据</div>
  {evidence_html}

  <div class="section-title">逐轮 Critic 决策</div>
  {critiques_html}

  <div class="section-title">动态计划修订</div>
  {revisions_html}

  {audit_html}
</body>
</html>
"""

    story = fitz.Story(html=full_html)
    with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_file:
        writer = fitz.DocumentWriter(tmp_file.name)
        more = True
        while more:
            device = writer.begin_page(fitz.Rect(0, 0, 595, 842))
            more, _ = story.place(fitz.Rect(40, 45, 555, 797))
            story.draw(device)
            writer.end_page()
        writer.close()
        with open(tmp_file.name, "rb") as f:
            pdf_bytes = f.read()

    return pdf_bytes
