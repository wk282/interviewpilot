import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.interview import (
    InterviewAnswer,
    InterviewEvaluation,
    InterviewPlan,
    InterviewQualityAudit,
    InterviewQuestion,
    InterviewSession,
    InterviewTurnCritique,
)


AUDIT_VERSION = "business-quality-v1"
DIFFICULTY_RANK = {"EASY": 0, "MEDIUM": 1, "HARD": 2}
REPORT_DIMENSIONS = {
    "technical_depth",
    "project_authenticity",
    "problem_solving",
    "system_design",
    "communication",
}


def ratio(numerator: int, denominator: int, *, empty_value: float = 1.0) -> float:
    return round(numerator / denominator, 4) if denominator else empty_value


def section_competencies(section: object) -> list[str]:
    if not isinstance(section, dict) or not isinstance(section.get("competencies"), list):
        return []
    return [str(item).strip() for item in section["competencies"] if str(item).strip()]


def normalized_bigrams(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def similarity(left: str, right: str) -> float:
    left_terms = normalized_bigrams(left)
    right_terms = normalized_bigrams(right)
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 0.0


def repeated_question_count(questions: list[InterviewQuestion]) -> int:
    repeated = 0
    for index, question in enumerate(questions[1:], start=1):
        if max(
            (similarity(question.content, previous.content) for previous in questions[:index]),
            default=0.0,
        ) >= 0.78:
            repeated += 1
    return repeated


def adaptive_action_compliant(
    question: InterviewQuestion,
    previous: InterviewQuestion | None,
    action: str,
) -> bool:
    is_follow_up = question.generated_by == "FOLLOW_UP" or question.parent_question_id is not None
    if action == "FOLLOW_UP":
        return is_follow_up
    if action == "INCREASE_DIFFICULTY":
        previous_rank = DIFFICULTY_RANK.get(previous.difficulty, 1) if previous else 1
        current_rank = DIFFICULTY_RANK.get(question.difficulty, 1)
        return bool(
            previous
            and is_follow_up
            and (
                current_rank > previous_rank
                or (previous_rank == max(DIFFICULTY_RANK.values()) and current_rank == previous_rank)
            )
        )
    if action == "DECREASE_DIFFICULTY":
        previous_rank = DIFFICULTY_RANK.get(previous.difficulty, 1) if previous else 1
        current_rank = DIFFICULTY_RANK.get(question.difficulty, 1)
        return bool(
            previous
            and is_follow_up
            and (
                current_rank < previous_rank
                or (previous_rank == min(DIFFICULTY_RANK.values()) and current_rank == previous_rank)
            )
        )
    if action == "SWITCH_TOPIC":
        return bool(
            previous
            and question.competency
            and previous.competency
            and question.competency != previous.competency
        )
    return action != "END_INTERVIEW"


def make_gate(
    key: str,
    label: str,
    value: float | bool,
    threshold: float | bool,
    passed: bool,
    *,
    required: bool = True,
) -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "threshold": threshold,
        "passed": passed,
        "required": required,
    }


async def generate_interview_quality_audit(
    session: AsyncSession,
    interview: InterviewSession,
    evaluation: InterviewEvaluation,
) -> InterviewQualityAudit:
    await session.scalar(
        select(InterviewSession.id)
        .where(InterviewSession.id == interview.id)
        .with_for_update()
    )
    existing = await session.scalar(
        select(InterviewQualityAudit).where(
            InterviewQualityAudit.interview_session_id == interview.id,
            InterviewQualityAudit.audit_version == AUDIT_VERSION,
        )
    )
    if existing is not None:
        return existing
    if interview.status != "COMPLETED" or evaluation.status != "COMPLETED":
        raise ValueError("Interview and evaluation must be completed before quality audit")

    plan = await session.scalar(
        select(InterviewPlan)
        .where(
            InterviewPlan.interview_session_id == interview.id,
            InterviewPlan.status == "READY",
        )
        .order_by(InterviewPlan.version.desc())
        .limit(1)
    )
    rows = (
        await session.execute(
            select(InterviewQuestion, InterviewAnswer)
            .outerjoin(
                InterviewAnswer,
                InterviewAnswer.interview_question_id == InterviewQuestion.id,
            )
            .where(InterviewQuestion.interview_session_id == interview.id)
            .order_by(InterviewQuestion.order_no)
        )
    ).all()
    questions = [question for question, _ in rows]
    answers = {
        question.id: answer
        for question, answer in rows
        if answer is not None
    }
    critiques = list(
        (
            await session.scalars(
                select(InterviewTurnCritique).where(
                    InterviewTurnCritique.interview_session_id == interview.id
                )
            )
        ).all()
    )
    critique_by_question = {
        critique.interview_question_id: critique for critique in critiques
    }

    target_competencies = {
        competency
        for section in (plan.sections if plan else [])
        for competency in section_competencies(section)
    }
    covered_competencies = {
        question.competency
        for question in questions
        if question.id in answers and question.competency
    }
    answered_count = len(answers)
    answered_rate = ratio(answered_count, len(questions), empty_value=0.0)
    competency_coverage_rate = ratio(
        len(covered_competencies & target_competencies),
        len(target_competencies),
    )
    critic_coverage_rate = ratio(
        sum(question_id in critique_by_question for question_id in answers),
        answered_count,
    )

    adaptive_count = 0
    adaptive_compliant_count = 0
    for index, question in enumerate(questions):
        metadata = question.decision_metadata if isinstance(question.decision_metadata, dict) else {}
        action = metadata.get("adaptive_action")
        if not isinstance(action, str):
            continue
        adaptive_count += 1
        previous = questions[index - 1] if index > 0 else None
        if adaptive_action_compliant(question, previous, action):
            adaptive_compliant_count += 1
    adaptive_compliance_rate = ratio(adaptive_compliant_count, adaptive_count)

    relevant_questions = [
        question
        for question in questions
        if question.question_type not in {"INTRODUCTION", "BEHAVIORAL", "CANDIDATE_QUESTION"}
    ]
    grounded_count = sum(bool(question.source_evidence) for question in relevant_questions)
    evidence_grounding_rate = ratio(grounded_count, len(relevant_questions))
    repeated_count = repeated_question_count(questions)
    repetition_rate = ratio(repeated_count, max(0, len(questions) - 1), empty_value=0.0)

    valid_report_evidence = 0
    cited_question_ids: set[uuid.UUID] = set()
    for item in evaluation.evidence:
        if not isinstance(item, dict):
            continue
        try:
            question_id = uuid.UUID(str(item.get("question_id")))
        except (TypeError, ValueError):
            continue
        answer = answers.get(question_id)
        excerpt = str(item.get("answer_excerpt") or "").strip()
        if answer is not None and excerpt and excerpt in answer.content:
            valid_report_evidence += 1
            cited_question_ids.add(question_id)
    report_evidence_validity_rate = ratio(
        valid_report_evidence,
        len(evaluation.evidence),
        empty_value=0.0,
    )
    report_evidence_coverage_rate = ratio(
        len(cited_question_ids),
        answered_count,
        empty_value=0.0,
    )
    dimension_complete = set(evaluation.dimension_scores) == REPORT_DIMENSIONS
    average_critic_score = (
        sum(float(item.score) for item in critiques) / len(critiques)
        if critiques
        else None
    )
    score_consistency_gap = (
        round(abs(average_critic_score - float(evaluation.overall_score)), 2)
        if average_critic_score is not None and evaluation.overall_score is not None
        else None
    )
    fallback_turn_count = 0
    for question in questions:
        metadata = question.decision_metadata if isinstance(question.decision_metadata, dict) else {}
        observability = metadata.get("observability")
        conductor = observability.get("conductor", {}) if isinstance(observability, dict) else {}
        retrieval_trace = metadata.get("retrieval_trace")
        retrieval_fallback = bool(
            isinstance(retrieval_trace, list)
            and any(
                isinstance(node, dict)
                and (
                    node.get("grading_source") == "fallback_rule"
                    or (node.get("node") == "web_search" and node.get("error"))
                )
                for node in retrieval_trace
            )
        )
        critique = critique_by_question.get(question.id)
        if (
            isinstance(conductor, dict)
            and conductor.get("source") not in {None, "model"}
        ) or (
            critique is not None and critique.decision_source == "FALLBACK_RULE"
        ) or retrieval_fallback:
            fallback_turn_count += 1
    fallback_turn_rate = ratio(fallback_turn_count, len(questions), empty_value=0.0)

    metrics = {
        "question_count": len(questions),
        "answered_count": answered_count,
        "answered_rate": answered_rate,
        "target_competency_count": len(target_competencies),
        "covered_competency_count": len(covered_competencies & target_competencies),
        "competency_coverage_rate": competency_coverage_rate,
        "critic_coverage_rate": critic_coverage_rate,
        "adaptive_action_count": adaptive_count,
        "adaptive_compliance_rate": adaptive_compliance_rate,
        "evidence_grounding_rate": evidence_grounding_rate,
        "repeated_question_count": repeated_count,
        "question_repetition_rate": repetition_rate,
        "report_evidence_validity_rate": report_evidence_validity_rate,
        "report_evidence_coverage_rate": report_evidence_coverage_rate,
        "report_dimension_complete": dimension_complete,
        "average_critic_score": round(average_critic_score, 2) if average_critic_score is not None else None,
        "final_overall_score": float(evaluation.overall_score) if evaluation.overall_score is not None else None,
        "score_consistency_gap": score_consistency_gap,
        "fallback_turn_rate": fallback_turn_rate,
    }
    gates = [
        make_gate("answered_rate", "有效作答率", answered_rate, 0.8, answered_rate >= 0.8),
        make_gate("competency_coverage", "计划能力覆盖率", competency_coverage_rate, 0.7, competency_coverage_rate >= 0.7),
        make_gate("critic_coverage", "Critic 覆盖率", critic_coverage_rate, 0.9, critic_coverage_rate >= 0.9),
        make_gate("adaptive_compliance", "动态计划执行一致率", adaptive_compliance_rate, 0.8, adaptive_compliance_rate >= 0.8),
        make_gate("evidence_grounding", "问题证据支撑率", evidence_grounding_rate, 0.4, evidence_grounding_rate >= 0.4),
        make_gate("question_repetition", "问题重复率", repetition_rate, 0.2, repetition_rate <= 0.2),
        make_gate("report_evidence_validity", "报告证据有效率", report_evidence_validity_rate, 0.95, report_evidence_validity_rate >= 0.95),
        make_gate("report_evidence_coverage", "报告证据覆盖率", report_evidence_coverage_rate, 0.4, report_evidence_coverage_rate >= 0.4),
        make_gate("report_dimensions", "报告评分维度完整", dimension_complete, True, dimension_complete),
        make_gate("fallback_turn_rate", "降级题目比例", fallback_turn_rate, 0.3, fallback_turn_rate <= 0.3),
        make_gate(
            "score_consistency",
            "逐轮评分与最终评分偏差",
            score_consistency_gap if score_consistency_gap is not None else 0.0,
            25.0,
            score_consistency_gap is None or score_consistency_gap <= 25.0,
            required=False,
        ),
    ]
    warnings = [
        f"{gate['label']}未通过质量门禁"
        for gate in gates
        if gate["required"] and not gate["passed"]
    ]
    if len(questions) < 5:
        warnings.append("面试题目少于 5 道，业务指标样本量偏小")
    if adaptive_count == 0:
        warnings.append("未检测到动态计划动作，无法充分验证多智能体反馈闭环")
    if not target_competencies:
        warnings.append("面试蓝图没有可审计的目标能力点")
    passed = all(gate["passed"] for gate in gates if gate["required"])
    audit = InterviewQualityAudit(
        interview_session_id=interview.id,
        audit_version=AUDIT_VERSION,
        passed=passed,
        metrics=metrics,
        quality_gates=gates,
        warnings=warnings,
        generated_at=datetime.now(timezone.utc),
    )
    session.add(audit)
    await session.flush()
    return audit
