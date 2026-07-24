from __future__ import annotations

import operator
import uuid
from dataclasses import asdict
from time import perf_counter
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.interview import (
    CandidateProfile,
    InterviewAnswer,
    InterviewEvaluation,
    InterviewPlan,
    InterviewPlanRevision,
    InterviewQuestion,
    InterviewSession,
    InterviewTurnCritique,
    JobPosition,
)
from app.db.models.user import AppUser
from app.core.logger import logger
from app.services.ai_observability import elapsed_ms
from app.services.answer_critic import CRITIC_PROMPT_VERSION, critique_answer
from app.services.interview_conductor import (
    CONDUCTOR_PROMPT_VERSION,
    GeneratedTurn,
    generate_next_turn,
)
from app.services.interview_checkpointing import (
    checkpoint_config,
    checkpoint_thread_id,
    interview_checkpointer,
)
from app.services.interview_evaluator import EVALUATION_PROMPT_VERSION, evaluate_interview
from app.services.interview_plan_reviser import (
    guidance_from_revision,
    revise_interview_plan,
)
from app.services.interview_planner import PROMPT_VERSION, generate_plan


AgentRequest = Literal["PLAN", "TURN", "EVALUATE"]


class InterviewState(TypedDict, total=False):
    request_type: AgentRequest
    interview_id: str
    user_id: str
    plan_id: str
    question_id: str | None
    answer_id: str | None
    question_skipped: bool
    resume_pending: bool
    finish_interview: bool
    critique_id: str | None
    plan_revision_id: str | None
    evaluation_id: str
    plan_version: int
    adaptive_guidance: dict
    generated_turn: dict
    retrieved_evidence: list[dict]
    retrieval_grade: dict
    remaining_question_budget: int
    next_action: str
    status: str
    pause_reason: str | None
    checkpoint_thread_id: str
    error: str | None
    execution_trace: Annotated[list[dict], operator.add]


class InterviewAgentGraph:
    """Unified LangGraph entry point for all interview agents.

    The graph state contains only serializable identifiers and payloads. Database
    models stay inside nodes so PostgreSQL checkpoints never serialize ORM state.
    """

    def __init__(
        self,
        session: AsyncSession,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        self.session = session
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(InterviewState)
        graph.add_node("request_router", self.request_router_node)
        graph.add_node("planner_agent", self.planner_agent_node)
        graph.add_node("answer_critic_agent", self.answer_critic_agent_node)
        graph.add_node("plan_reviser_agent", self.plan_reviser_agent_node)
        graph.add_node("interviewer_agent", self.interviewer_agent_node)
        graph.add_node("wait_for_answer", self.wait_for_answer_node)
        graph.add_node("final_evaluator_agent", self.final_evaluator_agent_node)
        graph.set_entry_point("request_router")
        graph.add_conditional_edges(
            "request_router",
            self.route_request,
            {
                "planner_agent": "planner_agent",
                "answer_critic_agent": "answer_critic_agent",
                "interviewer_agent": "interviewer_agent",
                "final_evaluator_agent": "final_evaluator_agent",
            },
        )
        graph.add_edge("answer_critic_agent", "plan_reviser_agent")
        graph.add_edge("plan_reviser_agent", "interviewer_agent")
        graph.add_edge("planner_agent", END)
        graph.add_conditional_edges(
            "interviewer_agent",
            self.route_after_interviewer,
            {"wait_for_answer": "wait_for_answer", "end": END},
        )
        graph.add_conditional_edges(
            "wait_for_answer",
            self.route_after_resume,
            {
                "answer_critic_agent": "answer_critic_agent",
                "interviewer_agent": "interviewer_agent",
                "end": END,
            },
        )
        graph.add_edge("final_evaluator_agent", END)
        if self.checkpointer is None:
            return graph.compile()
        return graph.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["wait_for_answer"],
        )

    async def request_router_node(self, state: InterviewState) -> dict:
        request_type = state.get("request_type")
        if request_type not in {"PLAN", "TURN", "EVALUATE"}:
            raise ValueError("Unsupported interview agent request")
        route = self.route_request(state)
        logger.info(
            f"Agent route selected | interview_id={state.get('interview_id')} | "
            f"request_type={request_type} | route={route}"
        )
        return {
            "status": "ROUTED",
            "execution_trace": [
                {
                    "node": "request_router",
                    "request_type": request_type,
                    "route_reason": route,
                }
            ],
        }

    @staticmethod
    def route_request(state: InterviewState) -> str:
        request_type = state.get("request_type")
        if request_type == "PLAN":
            return "planner_agent"
        if request_type == "EVALUATE":
            return "final_evaluator_agent"
        if state.get("question_id") and state.get("answer_id"):
            return "answer_critic_agent"
        return "interviewer_agent"

    @staticmethod
    def route_after_interviewer(state: InterviewState) -> str:
        return "wait_for_answer" if state.get("next_action") == "ASK" else "end"

    @staticmethod
    def route_after_resume(state: InterviewState) -> str:
        if state.get("next_action") == "FINISH":
            return "end"
        return (
            "interviewer_agent"
            if state.get("question_skipped")
            else "answer_critic_agent"
        )

    async def planner_agent_node(self, state: InterviewState) -> dict:
        started_at = perf_counter()
        logger.info(
            f"Agent node started | node=planner_agent | "
            f"interview_id={state.get('interview_id')} | plan_id={state.get('plan_id')}"
        )
        plan = await self.session.get(InterviewPlan, uuid.UUID(state["plan_id"]))
        interview = await self.session.get(
            InterviewSession, uuid.UUID(state["interview_id"])
        )
        user = await self.session.get(AppUser, uuid.UUID(state["user_id"]))
        if plan is None or interview is None or user is None:
            raise ValueError("Planner Agent context is incomplete")
        position = await self.session.get(JobPosition, interview.job_position_id)
        candidate = await self.session.get(
            CandidateProfile, interview.candidate_profile_id
        )
        if position is None or candidate is None:
            raise ValueError("Planner Agent business context is incomplete")
        await generate_plan(self.session, plan, interview, position, candidate, user)
        logger.info(
            f"Agent node completed | node=planner_agent | interview_id={interview.id} | "
            f"plan_id={plan.id} | version={plan.version} | latency_ms={elapsed_ms(started_at)}"
        )
        return {
            "status": "PLANNED",
            "plan_version": plan.version,
            "next_action": "WAIT_FOR_INTERVIEW_START",
            "execution_trace": [
                {
                    "node": "planner_agent",
                    "role": "生成面试目标和能力蓝图",
                    "tools": ["knowledge_retrieval", "reranker"],
                    "plan_id": str(plan.id),
                    "plan_version": plan.version,
                    "prompt_version": PROMPT_VERSION,
                    "model": plan.model_name,
                    "latency_ms": elapsed_ms(started_at),
                }
            ],
        }

    async def answer_critic_agent_node(self, state: InterviewState) -> dict:
        started_at = perf_counter()
        logger.info(
            f"Agent node started | node=answer_critic_agent | "
            f"interview_id={state.get('interview_id')} | "
            f"question_id={state.get('question_id')} | answer_id={state.get('answer_id')}"
        )
        interview = await self.session.get(
            InterviewSession, uuid.UUID(state["interview_id"])
        )
        question = await self.session.get(
            InterviewQuestion, uuid.UUID(state["question_id"])
        )
        answer = await self.session.get(
            InterviewAnswer, uuid.UUID(state["answer_id"])
        )
        if interview is None or question is None or answer is None:
            raise ValueError("Answer Critic Agent context is incomplete")
        if question.interview_session_id != interview.id or answer.interview_session_id != interview.id:
            raise ValueError("Answer Critic Agent context crosses interview boundaries")
        critique, observability = await critique_answer(
            self.session, interview, question, answer
        )
        # The checkpoint written after this node references these business IDs.
        # Commit them first so a restarted Reviser never receives stale IDs.
        await self.session.commit()
        await self.session.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == interview.id)
            .with_for_update()
        )
        logger.info(
            f"Agent node completed | node=answer_critic_agent | "
            f"interview_id={interview.id} | critique_id={critique.id} | "
            f"score={float(critique.score):.1f} | action={critique.next_action} | "
            f"source={critique.decision_source} | latency_ms={elapsed_ms(started_at)}"
        )
        return {
            "status": "CRITIQUED",
            "critique_id": str(critique.id),
            "next_action": critique.next_action,
            "execution_trace": [
                {
                    "node": "answer_critic_agent",
                    "role": "评价回答并决定后续动作",
                    "tools": ["answer_evaluation", "question_evidence"],
                    "critique_id": str(critique.id),
                    "score": float(critique.score),
                    "next_action": critique.next_action,
                    "decision_source": critique.decision_source,
                    "prompt_version": CRITIC_PROMPT_VERSION,
                    "latency_ms": elapsed_ms(started_at),
                    "observability": observability,
                }
            ],
        }

    async def plan_reviser_agent_node(self, state: InterviewState) -> dict:
        started_at = perf_counter()
        logger.info(
            f"Agent node started | node=plan_reviser_agent | "
            f"interview_id={state.get('interview_id')} | critique_id={state.get('critique_id')}"
        )
        interview = await self.session.get(
            InterviewSession, uuid.UUID(state["interview_id"])
        )
        question = await self.session.get(
            InterviewQuestion, uuid.UUID(state["question_id"])
        )
        critique = await self.session.get(
            InterviewTurnCritique, uuid.UUID(state["critique_id"])
        )
        if interview is None or question is None or critique is None:
            raise ValueError("Plan Reviser Agent context is incomplete")
        revision, guidance = await revise_interview_plan(
            self.session, interview, question, critique
        )
        # Persist the answered turn before the graph calls the next model. This
        # keeps business rows aligned with a checkpoint that may outlive HTTP.
        await self.session.commit()
        await self.session.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == interview.id)
            .with_for_update()
        )
        logger.info(
            f"Agent node completed | node=plan_reviser_agent | "
            f"interview_id={interview.id} | revision_id={revision.id} | "
            f"version={revision.version} | action={revision.action} | "
            f"remaining_budget={revision.remaining_question_budget} | "
            f"latency_ms={elapsed_ms(started_at)}"
        )
        return {
            "status": "REVISED",
            "plan_revision_id": str(revision.id),
            "plan_version": revision.version,
            "adaptive_guidance": guidance.as_payload(),
            "remaining_question_budget": revision.remaining_question_budget,
            "next_action": revision.action,
            "execution_trace": [
                {
                    "node": "plan_reviser_agent",
                    "role": "修订计划并重新分配题目预算",
                    "tools": ["plan_snapshot", "competency_budget"],
                    "revision_id": str(revision.id),
                    "version": revision.version,
                    "action": revision.action,
                    "change_set": dict(revision.change_set),
                    "remaining_question_budget": revision.remaining_question_budget,
                    "latency_ms": elapsed_ms(started_at),
                }
            ],
        }

    async def interviewer_agent_node(self, state: InterviewState) -> dict:
        started_at = perf_counter()
        logger.info(
            f"Agent node started | node=interviewer_agent | "
            f"interview_id={state.get('interview_id')} | "
            f"plan_revision_id={state.get('plan_revision_id')}"
        )
        interview = await self.session.get(
            InterviewSession, uuid.UUID(state["interview_id"])
        )
        user = await self.session.get(AppUser, uuid.UUID(state["user_id"]))
        if interview is None or user is None:
            raise ValueError("Interviewer Agent context is incomplete")
        guidance = None
        if state.get("plan_revision_id") and state.get("critique_id"):
            revision = await self.session.get(
                InterviewPlanRevision, uuid.UUID(state["plan_revision_id"])
            )
            critique = await self.session.get(
                InterviewTurnCritique, uuid.UUID(state["critique_id"])
            )
            if revision is None or critique is None:
                raise ValueError("Interviewer Agent adaptive context is incomplete")
            guidance = guidance_from_revision(revision, critique)
        turn = await generate_next_turn(
            self.session, interview, user, guidance=guidance
        )
        turn_payload = asdict(turn)
        logger.info(
            f"Agent node completed | node=interviewer_agent | "
            f"interview_id={interview.id} | action={turn.action} | "
            f"competency={turn.competency} | difficulty={turn.difficulty} | "
            f"adaptive_action={turn.adaptive_action} | latency_ms={elapsed_ms(started_at)}"
        )
        return {
            "status": "WAITING_FOR_ANSWER" if turn.action == "ASK" else "FINISHED",
            "generated_turn": turn_payload,
            "retrieved_evidence": list(turn.source_evidence or []),
            "retrieval_grade": dict(turn.retrieval_grade or {}),
            "next_action": turn.action,
            "pause_reason": "WAIT_FOR_ANSWER" if turn.action == "ASK" else None,
            "execution_trace": [
                {
                    "node": "interviewer_agent",
                    "role": "基于计划、反馈和 CRAG 生成下一题",
                    "tools": ["agentic_crag", "question_generation"],
                    "action": turn.action,
                    "competency": turn.competency,
                    "difficulty": turn.difficulty,
                    "prompt_version": CONDUCTOR_PROMPT_VERSION,
                    "latency_ms": elapsed_ms(started_at),
                    "observability": turn.observability or {},
                }
            ],
        }

    async def wait_for_answer_node(self, state: InterviewState) -> dict:
        if state.get("finish_interview") is True:
            logger.info(
                f"Agent runtime resumed | node=wait_for_answer | "
                f"interview_id={state.get('interview_id')} | action=FINISH"
            )
            return {
                "next_action": "FINISH",
                "pause_reason": None,
                "resume_pending": False,
                "finish_interview": False,
                "status": "FINISHED",
                "execution_trace": [
                    {
                        "node": "wait_for_answer",
                        "resume_action": "FINISH",
                    }
                ],
            }
        question_id = state.get("question_id")
        answer_id = state.get("answer_id")
        question_skipped = bool(state.get("question_skipped"))
        if not question_id:
            raise ValueError("Interview resume payload is missing question_id")
        if not question_skipped and not answer_id:
            raise ValueError("Interview resume payload is missing answer_id")
        logger.info(
            f"Agent runtime resumed | node=wait_for_answer | "
            f"interview_id={state.get('interview_id')} | "
            f"question_id={question_id} | action={'SKIP' if question_skipped else 'ANSWER'}"
        )
        return {
            "question_id": str(question_id),
            "answer_id": str(answer_id) if answer_id else None,
            "question_skipped": question_skipped,
            "critique_id": None,
            "plan_revision_id": None,
            "adaptive_guidance": {},
            "pause_reason": None,
            "resume_pending": False,
            "finish_interview": False,
            "status": "RESUMED",
            "execution_trace": [
                {
                    "node": "wait_for_answer",
                    "resume_action": "SKIP" if question_skipped else "ANSWER",
                    "question_id": str(question_id),
                    "answer_id": str(answer_id) if answer_id else None,
                }
            ],
        }

    async def final_evaluator_agent_node(self, state: InterviewState) -> dict:
        started_at = perf_counter()
        logger.info(
            f"Agent node started | node=final_evaluator_agent | "
            f"interview_id={state.get('interview_id')} | "
            f"evaluation_id={state.get('evaluation_id')}"
        )
        evaluation = await self.session.get(
            InterviewEvaluation, uuid.UUID(state["evaluation_id"])
        )
        interview = await self.session.get(
            InterviewSession, uuid.UUID(state["interview_id"])
        )
        if evaluation is None or interview is None:
            raise ValueError("Final Evaluator Agent context is incomplete")
        await evaluate_interview(self.session, evaluation, interview)
        logger.info(
            f"Agent node completed | node=final_evaluator_agent | "
            f"interview_id={interview.id} | evaluation_id={evaluation.id} | "
            f"score={evaluation.overall_score} | recommendation={evaluation.recommendation} | "
            f"latency_ms={elapsed_ms(started_at)}"
        )
        return {
            "status": "EVALUATED",
            "next_action": "REPORT_READY",
            "execution_trace": [
                {
                    "node": "final_evaluator_agent",
                    "role": "基于回答证据生成最终评分报告",
                    "tools": ["evidence_scoring", "report_generation"],
                    "evaluation_id": str(evaluation.id),
                    "prompt_version": EVALUATION_PROMPT_VERSION,
                    "model": evaluation.model_name,
                    "latency_ms": elapsed_ms(started_at),
                }
            ],
        }

    async def invoke(
        self,
        graph_input: InterviewState | None,
        config: dict | None = None,
    ) -> InterviewState:
        return await self.graph.ainvoke(graph_input, config=config or {})

    async def update_state(self, config: dict, values: dict) -> None:
        await self.graph.aupdate_state(config, values)


async def run_planner_agent_graph(
    session: AsyncSession,
    plan: InterviewPlan,
    interview: InterviewSession,
    user: AppUser,
) -> InterviewState:
    return await InterviewAgentGraph(session).invoke(
        {
            "request_type": "PLAN",
            "interview_id": str(interview.id),
            "user_id": str(user.id),
            "plan_id": str(plan.id),
            "execution_trace": [],
        }
    )


async def run_interview_turn_agent_graph(
    session: AsyncSession,
    interview: InterviewSession,
    user: AppUser,
    *,
    question: InterviewQuestion | None = None,
    answer: InterviewAnswer | None = None,
) -> tuple[GeneratedTurn, list[dict]]:
    graph_started_at = perf_counter()
    logger.info(
        f"Interview runtime graph started | interview_id={interview.id} | "
        f"question_id={question.id if question else None} | "
        f"answer_id={answer.id if answer else None}"
    )
    config = checkpoint_config(interview.id, "runtime")
    initial: InterviewState = {
        "request_type": "TURN",
        "interview_id": str(interview.id),
        "user_id": str(user.id),
        "checkpoint_thread_id": checkpoint_thread_id(interview.id, "runtime"),
        "execution_trace": [],
    }
    if question is not None:
        initial["question_id"] = str(question.id)
        initial["answer_id"] = str(answer.id) if answer is not None else None
        initial["question_skipped"] = answer is None
    async with interview_checkpointer() as checkpointer:
        graph = InterviewAgentGraph(session, checkpointer)
        checkpoint = await checkpointer.aget_tuple(config)
        channel_values = (
            checkpoint.checkpoint.get("channel_values", {})
            if checkpoint is not None
            else {}
        )
        restores_uncommitted_turn = bool(
            question is not None
            and isinstance(channel_values, dict)
            and channel_values.get("question_id") == str(question.id)
            and channel_values.get("pause_reason") == "WAIT_FOR_ANSWER"
            and not channel_values.get("resume_pending")
            and channel_values.get("generated_turn")
        )
        restores_completed_turn = bool(
            question is not None
            and isinstance(channel_values, dict)
            and channel_values.get("question_id") == str(question.id)
            and channel_values.get("status") == "FINISHED"
            and channel_values.get("next_action") == "FINISH"
            and channel_values.get("generated_turn")
        )
        if restores_uncommitted_turn:
            state = channel_values
        elif restores_completed_turn:
            state = channel_values
        elif (
            question is not None
            and checkpoint is not None
            and isinstance(channel_values, dict)
            and channel_values.get("question_id") == str(question.id)
        ):
            state = await graph.invoke(None, config)
        elif question is not None and checkpoint is not None:
            await graph.update_state(
                config,
                {
                    "question_id": str(question.id),
                    "answer_id": str(answer.id) if answer is not None else None,
                    "question_skipped": answer is None,
                    "resume_pending": True,
                    "finish_interview": False,
                },
            )
            state = await graph.invoke(None, config)
        elif checkpoint is not None:
            if not isinstance(channel_values, dict) or not channel_values.get(
                "generated_turn"
            ):
                state = await graph.invoke(initial, config)
            else:
                state = channel_values
        else:
            state = await graph.invoke(initial, config)
    turn = GeneratedTurn(**state["generated_turn"])
    full_graph_trace = list(state.get("execution_trace", []))
    latest_resume_index = max(
        (
            index
            for index, item in enumerate(full_graph_trace)
            if item.get("node") == "wait_for_answer"
        ),
        default=0,
    )
    graph_trace = full_graph_trace[latest_resume_index:]
    if state.get("plan_revision_id"):
        revision = await session.get(
            InterviewPlanRevision, uuid.UUID(state["plan_revision_id"])
        )
        if revision is not None:
            revision.workflow_trace = graph_trace
            await session.flush()
    turn.observability = {
        **(turn.observability or {}),
        "agent_graph": {
            "request_type": "TURN",
            "status": state.get("status"),
            "next_action": state.get("next_action"),
            "plan_version": state.get("plan_version"),
            "remaining_question_budget": state.get("remaining_question_budget"),
            "thread_id": state.get("checkpoint_thread_id"),
            "checkpointed": True,
            "pause_reason": state.get("pause_reason"),
            "trace": graph_trace,
        },
    }
    logger.info(
        f"Interview runtime graph completed | interview_id={interview.id} | "
        f"action={turn.action} | trace_nodes={len(graph_trace)} | "
        f"latency_ms={elapsed_ms(graph_started_at)}"
    )
    return turn, graph_trace


async def run_final_evaluator_agent_graph(
    session: AsyncSession,
    evaluation: InterviewEvaluation,
    interview: InterviewSession,
) -> InterviewState:
    return await InterviewAgentGraph(session).invoke(
        {
            "request_type": "EVALUATE",
            "interview_id": str(interview.id),
            "evaluation_id": str(evaluation.id),
            "execution_trace": [],
        }
    )


async def finish_interview_runtime_agent_graph(
    session: AsyncSession,
    interview: InterviewSession,
) -> None:
    config = checkpoint_config(interview.id, "runtime")
    try:
        async with interview_checkpointer() as checkpointer:
            checkpoint = await checkpointer.aget_tuple(config)
            if checkpoint is None:
                return
            graph = InterviewAgentGraph(session, checkpointer)
            await graph.update_state(
                config,
                {
                    "finish_interview": True,
                    "resume_pending": True,
                },
            )
            await graph.invoke(None, config)
    except Exception as error:
        logger.warning(
            f"Failed to finish runtime checkpoint for interview {interview.id}: {error}"
        )
