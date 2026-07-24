from types import SimpleNamespace

from app.services.interview_quality_audit import (
    adaptive_action_compliant,
    repeated_question_count,
    similarity,
)


def question(
    content: str,
    *,
    competency: str = "RAG",
    difficulty: str = "MEDIUM",
    generated_by: str = "PLAN",
    parent_question_id=None,
):
    return SimpleNamespace(
        content=content,
        competency=competency,
        difficulty=difficulty,
        generated_by=generated_by,
        parent_question_id=parent_question_id,
    )


def test_similarity_detects_rephrased_duplicate() -> None:
    left = "请说明 RAG 系统中混合检索的实现方式。"
    right = "请说明RAG系统中混合检索的实现方式"
    unrelated = "请介绍你在项目中的职责和最终结果。"

    assert similarity(left, right) >= 0.78
    assert similarity(left, unrelated) < 0.78


def test_repeated_question_count_counts_later_duplicate_once() -> None:
    questions = [
        question("请说明 RAG 系统中混合检索的实现方式。"),
        question("请介绍项目中遇到的主要故障。"),
        question("请说明RAG系统中混合检索的实现方式"),
    ]

    assert repeated_question_count(questions) == 1


def test_adaptive_difficulty_and_topic_actions_are_checked() -> None:
    previous = question("上一题", competency="RAG", difficulty="MEDIUM")
    harder = question(
        "深入追问",
        competency="RAG",
        difficulty="HARD",
        generated_by="FOLLOW_UP",
        parent_question_id="question-id",
    )
    switched = question("切换主题", competency="Agent", difficulty="MEDIUM")

    assert adaptive_action_compliant(harder, previous, "INCREASE_DIFFICULTY")
    assert adaptive_action_compliant(switched, previous, "SWITCH_TOPIC")
    assert not adaptive_action_compliant(switched, previous, "FOLLOW_UP")


def test_adaptive_difficulty_accepts_boundary_clamping() -> None:
    hard = question("上一题", difficulty="HARD")
    hard_follow_up = question(
        "继续深入",
        difficulty="HARD",
        generated_by="FOLLOW_UP",
        parent_question_id="question-id",
    )

    assert adaptive_action_compliant(
        hard_follow_up, hard, "INCREASE_DIFFICULTY"
    )
