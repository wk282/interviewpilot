import json
from decimal import Decimal
from time import perf_counter
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.db.models.interview import (
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    InterviewTurnCritique,
)
from app.services.ai_observability import elapsed_ms, model_usage
from app.services.ai_concurrency import ai_concurrency_slot
from app.services.interview_gap_policy import filter_technical_gaps


CRITIC_PROMPT_VERSION = "answer-critic-v2-technical-gaps"
CRITIC_SYSTEM_PROMPT = (
    "你是技术面试 Answer Critic。只评价候选人实际回答，不得把题目、参考答案或检索证据"
    "当成候选人已经表达的内容。检查技术正确性、具体程度、逻辑和项目真实性。"
    "answer_evidence 必须逐字引用 answer 中的短句；无法引用时返回空数组。"
    "next_action 只能为 FOLLOW_UP、INCREASE_DIFFICULTY、DECREASE_DIFFICULTY、"
    "SWITCH_TOPIC、END_INTERVIEW。difficulty_delta 只能为 -1、0、1。"
    "仅输出 JSON：score、strengths、knowledge_gaps、answer_evidence、next_action、"
    "difficulty_delta、confidence、reason。score 为 0 到 100，confidence 为 0 到 1；"
    "strengths、knowledge_gaps、answer_evidence 必须是字符串数组。"
)
CRITIC_SYSTEM_PROMPT += (
    "knowledge_gaps 只能填写可继续考察的具体技术概念、机制、实现方法或工程权衡，"
    "不得填写术语使用、措辞、表达、语法等沟通评价，也不得填写完整的评价句。"
    "表达问题可以写入 reason，但不能作为 knowledge_gaps。"
)


def parse_json_content(content: str) -> dict:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.removeprefix("```json").removeprefix("```")
        normalized = normalized.removesuffix("```").strip()
    return json.loads(normalized)


class GeneratedCritique(BaseModel):
    score: float = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    answer_evidence: list[str] = Field(default_factory=list)
    next_action: Literal[
        "FOLLOW_UP",
        "INCREASE_DIFFICULTY",
        "DECREASE_DIFFICULTY",
        "SWITCH_TOPIC",
        "END_INTERVIEW",
    ]
    difficulty_delta: Literal[-1, 0, 1] = 0
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("strengths", "knowledge_gaps", "answer_evidence", mode="before")
    @classmethod
    def normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        return value

    @field_validator("knowledge_gaps")
    @classmethod
    def retain_technical_gaps(cls, value: list[str]) -> list[str]:
        return filter_technical_gaps(value)

    @field_validator("next_action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "DEEPEN": "FOLLOW_UP",
            "ASK_FOLLOW_UP": "FOLLOW_UP",
            "RAISE_DIFFICULTY": "INCREASE_DIFFICULTY",
            "LOWER_DIFFICULTY": "DECREASE_DIFFICULTY",
            "CHANGE_TOPIC": "SWITCH_TOPIC",
            "FINISH": "END_INTERVIEW",
            "END": "END_INTERVIEW",
        }
        return aliases.get(normalized, normalized)

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("%"):
                normalized = normalized[:-1]
            if "/" in normalized:
                numerator, denominator = normalized.split("/", 1)
                try:
                    return float(numerator) / float(denominator) * 100
                except (ValueError, ZeroDivisionError):
                    return value
            try:
                return float(normalized)
            except ValueError:
                return value
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> object:
        aliases = {
            "low": 0.35,
            "moderate": 0.6,
            "medium": 0.6,
            "high": 0.8,
        }
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in aliases:
                return aliases[normalized]
            if normalized.endswith("%"):
                try:
                    return float(normalized[:-1]) / 100
                except ValueError:
                    return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value / 100 if 1 < value <= 100 else value
        return value

    @field_validator("difficulty_delta", mode="before")
    @classmethod
    def normalize_difficulty_delta(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            aliases = {
                "increase": 1,
                "higher": 1,
                "decrease": -1,
                "lower": -1,
                "same": 0,
                "unchanged": 0,
            }
            if normalized in aliases:
                return aliases[normalized]
            try:
                return int(normalized)
            except ValueError:
                return value
        return value

    @model_validator(mode="after")
    def align_difficulty_delta(self):
        if self.next_action == "INCREASE_DIFFICULTY":
            self.difficulty_delta = 1
        elif self.next_action == "DECREASE_DIFFICULTY":
            self.difficulty_delta = -1
        elif self.next_action in {"SWITCH_TOPIC", "END_INTERVIEW"}:
            self.difficulty_delta = 0
        return self


def clean_list(values: list[str], limit: int = 6) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized[:500])
        if len(cleaned) >= limit:
            break
    return cleaned


def fallback_critique_values(
    content: str,
    difficulty: str,
    expected_points: list,
) -> GeneratedCritique:
    content = content.strip()
    expected = clean_list([str(item) for item in expected_points], 3)
    if len(content) < 40:
        return GeneratedCritique(
            score=25,
            strengths=[],
            knowledge_gaps=expected or ["回答缺少足够的技术细节"],
            answer_evidence=[content[:300]] if content else [],
            next_action="DECREASE_DIFFICULTY",
            difficulty_delta=-1,
            confidence=0.35,
            reason="模型不可用，依据回答长度执行保守降级决策",
        )
    if len(content) < 160:
        return GeneratedCritique(
            score=50,
            strengths=["回答包含可继续核实的内容"],
            knowledge_gaps=expected or ["需要补充实现过程和结果证据"],
            answer_evidence=[content[:300]],
            next_action="FOLLOW_UP",
            difficulty_delta=0,
            confidence=0.35,
            reason="模型不可用，依据回答完整度执行保守追问",
        )
    return GeneratedCritique(
        score=70,
        strengths=["回答提供了较完整的说明"],
        knowledge_gaps=[],
        answer_evidence=[content[:300]],
        next_action=(
            "INCREASE_DIFFICULTY" if difficulty != "HARD" else "SWITCH_TOPIC"
        ),
        difficulty_delta=1 if difficulty != "HARD" else 0,
        confidence=0.35,
        reason="模型不可用，依据回答完整度执行保守推进决策",
    )


def fallback_critique(question: InterviewQuestion, answer: InterviewAnswer) -> GeneratedCritique:
    return fallback_critique_values(
        answer.content, question.difficulty, question.expected_points
    )


async def generate_critique(
    payload: dict,
    observability: dict | None = None,
) -> GeneratedCritique:
    started_at = perf_counter()
    async with AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=45.0,
        max_retries=0,
    ) as client:
        async with ai_concurrency_slot(
            "answer_critic",
            settings.LLM_MINI_MODEL,
            metrics_sink=observability,
        ):
            response = await client.chat.completions.create(
                model=settings.LLM_MINI_MODEL,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
    if observability is not None:
        observability.update(
            {
                "model": settings.LLM_MINI_MODEL,
                "prompt_version": CRITIC_PROMPT_VERSION,
                "usage": model_usage(response),
                "latency_ms": elapsed_ms(started_at),
            }
        )
    return GeneratedCritique.model_validate(
        parse_json_content(response.choices[0].message.content or "")
    )


def validated_answer_evidence(answer: str, excerpts: list[str]) -> list[str]:
    valid: list[str] = []
    for excerpt in clean_list(excerpts, 5):
        normalized = excerpt.strip().strip('"').strip("'")
        if normalized and normalized in answer and normalized not in valid:
            valid.append(normalized[:500])
    return valid or ([answer[:300]] if answer else [])


async def critique_answer(
    session: AsyncSession,
    interview: InterviewSession,
    question: InterviewQuestion,
    answer: InterviewAnswer,
) -> tuple[InterviewTurnCritique, dict]:
    started_at = perf_counter()
    existing = await session.scalar(
        select(InterviewTurnCritique).where(
            InterviewTurnCritique.interview_answer_id == answer.id
        )
    )
    if existing is not None:
        return existing, {
            "source": "persisted_result",
            "model": existing.model_name,
            "prompt_version": existing.prompt_version,
            "usage": {},
            "latency_ms": elapsed_ms(started_at),
        }

    payload = {
        "interview_mode": interview.mode,
        "question": {
            "content": question.content,
            "competency": question.competency,
            "difficulty": question.difficulty,
            "expected_points": question.expected_points,
        },
        "answer": answer.content[:6000],
        "reference_evidence": [
            {
                "filename": item.get("filename"),
                "content": str(item.get("content") or item.get("context") or "")[:1200],
            }
            for item in question.source_evidence[:4]
            if isinstance(item, dict)
        ],
    }
    decision_source = "MODEL"
    error_message = None
    observability: dict = {}
    try:
        generated = await generate_critique(payload, observability)
    except Exception as error:
        logger.warning(f"Answer Critic failed, using fallback: {error}")
        decision_source = "FALLBACK_RULE"
        error_message = f"{type(error).__name__}: {error}"[:2000]
        generated = fallback_critique(question, answer)
        observability.update(
            {
                "model": settings.LLM_MINI_MODEL,
                "prompt_version": CRITIC_PROMPT_VERSION,
                "usage": observability.get("usage", {}),
                "latency_ms": elapsed_ms(started_at),
                "error": error_message,
            }
        )

    critique = InterviewTurnCritique(
        interview_session_id=interview.id,
        interview_question_id=question.id,
        interview_answer_id=answer.id,
        score=Decimal(str(generated.score)),
        strengths=clean_list(generated.strengths),
        knowledge_gaps=clean_list(generated.knowledge_gaps),
        answer_evidence=validated_answer_evidence(
            answer.content, generated.answer_evidence
        ),
        next_action=generated.next_action,
        difficulty_delta=generated.difficulty_delta,
        confidence=Decimal(str(generated.confidence)),
        reason=generated.reason.strip(),
        decision_source=decision_source,
        model_name=settings.LLM_MINI_MODEL if decision_source == "MODEL" else None,
        prompt_version=CRITIC_PROMPT_VERSION,
        error_message=error_message,
    )
    session.add(critique)
    await session.flush()
    observability["source"] = decision_source.lower()
    observability["total_latency_ms"] = elapsed_ms(started_at)
    return critique, observability
