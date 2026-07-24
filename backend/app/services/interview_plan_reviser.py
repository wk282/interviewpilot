import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.interview import (
    InterviewPlan,
    InterviewPlanRevision,
    InterviewQuestion,
    InterviewSession,
    InterviewTurnCritique,
)
from app.services.interview_gap_policy import filter_technical_gaps


DIFFICULTIES = ["EASY", "MEDIUM", "HARD"]


@dataclass
class AdaptiveGuidance:
    critique_id: uuid.UUID
    plan_revision_id: uuid.UUID
    plan_version: int
    action: str
    target_competency: str | None
    target_difficulty: str | None
    knowledge_gaps: list[str]
    rationale: str
    score: float
    remaining_question_budget: int
    competency_budget: dict[str, int]

    def as_payload(self) -> dict:
        return {
            "action": self.action,
            "target_competency": self.target_competency,
            "target_difficulty": self.target_difficulty,
            "knowledge_gaps": self.knowledge_gaps,
            "rationale": self.rationale,
            "score": self.score,
            "plan_version": self.plan_version,
            "remaining_question_budget": self.remaining_question_budget,
            "competency_budget": self.competency_budget,
        }


def section_competencies(section: object) -> list[str]:
    if not isinstance(section, dict) or not isinstance(section.get("competencies"), list):
        return []
    return [str(item).strip() for item in section["competencies"] if str(item).strip()]


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def shift_difficulty(current: str, delta: int) -> str:
    current_index = DIFFICULTIES.index(current) if current in DIFFICULTIES else 1
    return DIFFICULTIES[max(0, min(len(DIFFICULTIES) - 1, current_index + delta))]


def allocate_competency_budget(
    priorities: list[str],
    remaining_question_budget: int,
) -> dict[str, int]:
    normalized_priorities = unique_strings(priorities)
    if remaining_question_budget <= 0 or not normalized_priorities:
        return {}
    budget = {competency: 0 for competency in normalized_priorities}
    for index in range(remaining_question_budget):
        competency = normalized_priorities[index % len(normalized_priorities)]
        budget[competency] += 1
    return {key: value for key, value in budget.items() if value > 0}


def revision_change_set(before: dict, after: dict) -> dict:
    changes: dict = {}
    for key in (
        "action",
        "target_competency",
        "target_difficulty",
        "covered_competencies",
        "priority_competencies",
        "knowledge_gaps",
        "remaining_question_budget",
        "competency_budget",
    ):
        if before.get(key) != after.get(key):
            changes[key] = {
                "before": before.get(key),
                "after": after.get(key),
            }
    return changes


def guidance_from_revision(
    revision: InterviewPlanRevision,
    critique: InterviewTurnCritique,
) -> AdaptiveGuidance:
    return AdaptiveGuidance(
        critique_id=critique.id,
        plan_revision_id=revision.id,
        plan_version=revision.version,
        action=revision.action,
        target_competency=revision.target_competency,
        target_difficulty=revision.target_difficulty,
        knowledge_gaps=filter_technical_gaps(revision.knowledge_gaps),
        rationale=revision.rationale,
        score=float(critique.score),
        remaining_question_budget=revision.remaining_question_budget,
        competency_budget=dict(revision.competency_budget),
    )


async def revise_interview_plan(
    session: AsyncSession,
    interview: InterviewSession,
    question: InterviewQuestion,
    critique: InterviewTurnCritique,
) -> tuple[InterviewPlanRevision, AdaptiveGuidance]:
    existing = await session.scalar(
        select(InterviewPlanRevision).where(
            InterviewPlanRevision.source_critique_id == critique.id
        )
    )
    if existing is not None:
        return existing, guidance_from_revision(existing, critique)

    plan = await session.scalar(
        select(InterviewPlan)
        .where(
            InterviewPlan.interview_session_id == interview.id,
            InterviewPlan.status == "READY",
        )
        .order_by(InterviewPlan.version.desc())
        .limit(1)
    )
    target_competencies = unique_strings(
        [
            competency
            for section in (plan.sections if plan else [])
            for competency in section_competencies(section)
        ]
    )
    rows = (
        await session.execute(
            select(InterviewQuestion, InterviewTurnCritique)
            .outerjoin(
                InterviewTurnCritique,
                InterviewTurnCritique.interview_question_id == InterviewQuestion.id,
            )
            .where(InterviewQuestion.interview_session_id == interview.id)
            .order_by(InterviewQuestion.order_no)
        )
    ).all()
    completed_count = sum(
        1 for asked_question, _ in rows if asked_question.status in {"ANSWERED", "SKIPPED"}
    )
    covered_competencies = unique_strings(
        [
            asked_question.competency
            for asked_question, turn_critique in rows
            if asked_question.competency
            and turn_critique is not None
            and Decimal(turn_critique.score) >= Decimal("60")
        ]
    )
    remaining_competencies = [
        item for item in target_competencies if item not in covered_competencies
    ]
    current_competency_count = sum(
        1
        for asked_question, _ in rows
        if asked_question.competency == question.competency
        and asked_question.status in {"ANSWERED", "SKIPPED"}
    )
    max_question_count = int(interview.configuration.get("max_question_count", 10))
    coverage_ratio = (
        len(set(covered_competencies) & set(target_competencies))
        / len(target_competencies)
        if target_competencies
        else 1.0
    )
    requested_action = critique.next_action
    action = requested_action
    override_reason = None
    if completed_count >= max_question_count:
        action = "END_INTERVIEW"
        override_reason = "已达到最大问题数"
    elif requested_action == "END_INTERVIEW" and (
        completed_count < 3 or coverage_ratio < 0.7
    ):
        action = "SWITCH_TOPIC"
        override_reason = "尚未满足最少题数或能力覆盖要求"
    elif requested_action in {
        "FOLLOW_UP",
        "INCREASE_DIFFICULTY",
        "DECREASE_DIFFICULTY",
    } and current_competency_count >= 3:
        action = "SWITCH_TOPIC"
        override_reason = "同一能力点已连续深挖，切换到未覆盖能力"
    elif requested_action == "SWITCH_TOPIC" and not remaining_competencies and completed_count >= 3:
        action = "END_INTERVIEW"
        override_reason = "计划能力点已覆盖"

    if action == "END_INTERVIEW":
        target_competency = None
        target_difficulty = None
    elif action == "SWITCH_TOPIC":
        target_competency = next(
            (item for item in remaining_competencies if item != question.competency),
            question.competency or "项目实践",
        )
        target_difficulty = "MEDIUM"
    else:
        target_competency = question.competency or "项目实践"
        target_difficulty = shift_difficulty(question.difficulty, critique.difficulty_delta)

    previous_revision = await session.scalar(
        select(InterviewPlanRevision)
        .where(InterviewPlanRevision.interview_session_id == interview.id)
        .order_by(InterviewPlanRevision.version.desc())
        .limit(1)
    )
    version = (previous_revision.version if previous_revision else 0) + 1
    knowledge_gaps = filter_technical_gaps(
        [
            *(previous_revision.knowledge_gaps if previous_revision else []),
            *critique.knowledge_gaps,
        ],
        limit=12,
    )
    priority_competencies = unique_strings(
        [target_competency or "", *remaining_competencies]
    )
    available_question_budget = max(0, max_question_count - completed_count)
    remaining_question_budget = (
        0 if action == "END_INTERVIEW" else available_question_budget
    )
    competency_budget = allocate_competency_budget(
        priority_competencies,
        remaining_question_budget,
    )
    rationale = critique.reason
    if override_reason:
        rationale = f"{critique.reason}；计划修正规则：{override_reason}"
    if previous_revision and previous_revision.after_snapshot:
        before_snapshot = dict(previous_revision.after_snapshot)
    else:
        before_priorities = unique_strings(
            [*remaining_competencies, question.competency or ""]
        )
        before_snapshot = {
            "base_plan_version": plan.version if plan else None,
            "action": "BASELINE",
            "target_competency": None,
            "target_difficulty": None,
            "covered_competencies": covered_competencies,
            "priority_competencies": before_priorities,
            "knowledge_gaps": [],
            "completed_question_count": completed_count,
            "remaining_question_budget": available_question_budget,
            "competency_budget": allocate_competency_budget(
                before_priorities,
                available_question_budget,
            ),
        }
    after_snapshot = {
        "base_plan_version": plan.version if plan else None,
        "action": action,
        "target_competency": target_competency,
        "target_difficulty": target_difficulty,
        "covered_competencies": covered_competencies,
        "priority_competencies": priority_competencies,
        "knowledge_gaps": knowledge_gaps,
        "completed_question_count": completed_count,
        "remaining_question_budget": remaining_question_budget,
        "competency_budget": competency_budget,
    }
    revision = InterviewPlanRevision(
        interview_session_id=interview.id,
        source_critique_id=critique.id,
        version=version,
        action=action,
        target_competency=target_competency,
        target_difficulty=target_difficulty,
        covered_competencies=covered_competencies,
        priority_competencies=priority_competencies,
        knowledge_gaps=knowledge_gaps,
        rationale=rationale,
        workflow_trace=[],
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        change_set=revision_change_set(before_snapshot, after_snapshot),
        remaining_question_budget=remaining_question_budget,
        competency_budget=competency_budget,
    )
    session.add(revision)
    await session.flush()
    return revision, guidance_from_revision(revision, critique)
