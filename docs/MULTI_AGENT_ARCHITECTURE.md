# Multi-Agent Interview Architecture

## Definition

InterviewPilot treats an agent as a bounded decision unit with a role, structured
state, tools, output contract, termination conditions, and execution trace. A
single LLM request without state routing or downstream control is not called an
agent.

## Unified State

`backend/app/services/interview_agent_graph.py` defines one serializable
`InterviewState`. It carries identifiers and structured payloads rather than ORM
objects, which keeps the state compatible with a persistent LangGraph
checkpointer without serializing SQLAlchemy sessions or ORM models.

Important fields include:

- request type: `PLAN`, `TURN`, or `EVALUATE`
- interview, user, plan, question, answer, critique, revision, and evaluation IDs
- adaptive guidance and remaining question budget
- retrieved evidence and retrieval grade
- generated turn and next action
- append-only execution trace

## Agents

| Agent | Responsibility | Allowed tools | Output |
| --- | --- | --- | --- |
| Planner | Build the initial objectives and competency blueprint | knowledge retrieval, reranker | versioned interview plan |
| Answer Critic | Evaluate only the candidate answer and select an action | answer evaluation, question evidence | score, gaps, evidence, action |
| Plan Reviser | Apply coverage and budget constraints | plan snapshot, competency budget | immutable revision and guidance |
| Interviewer | Generate one constrained next question | Agentic CRAG, question generation | `ASK` or `FINISH` |
| Final Evaluator | Produce an evidence-linked final report | evidence scoring, report generation | persisted evaluation report |

## Graph Routes

```text
PLAN
  request_router -> planner_agent -> END

TURN without an answer
  request_router -> interviewer_agent -> END

TURN with an answer
  request_router
    -> answer_critic_agent
    -> plan_reviser_agent
    -> interviewer_agent
    -> END

EVALUATE
  request_router -> final_evaluator_agent -> END
```

Human input is an intentional boundary. The graph ends after producing one
question, and the next HTTP request resumes from database state after the
candidate answers.

## Plan Revision

Every revision persists:

- before and after snapshots
- field-level change set
- reason and effective action
- covered and priority competencies
- remaining question budget
- per-competency budget
- complete per-turn Agent trace

The base `InterviewPlan` is not overwritten by a turn revision.

## Checkpoint And Human Pause

The runtime path uses the official asynchronous PostgreSQL checkpointer, with
state stored under `<interview_id>:runtime`. Planner and Final Evaluator are
one-shot Celery jobs and run through the same LangGraph without a checkpointer;
their retry and failure state is managed by Celery and the business tables.

After the Interviewer produces one question, the graph uses the compiled
`interrupt_before=["wait_for_answer"]` breakpoint and the HTTP request returns.
Submitting or skipping updates the checkpoint state and calls `ainvoke(None)` to
continue from the paused node instead of starting a new Critic workflow. If an
HTTP failure happens after checkpointing but before
the question row commits, the next runtime GET restores the generated turn from
the checkpoint without another model call.

Business state remains durable in the normal PostgreSQL tables. Runtime
checkpoints are workflow recovery data, not the source of truth. Deleting an
interview also removes its runtime checkpoint and any legacy checkpoint threads.

## Accurate Project Description

The project can now be described as a LangGraph-orchestrated multi-agent
interview platform because agent outputs route and constrain downstream agents.
Standalone AgentRun audit tables, administrative replay controls, and automated
fault-injection verification remain production reliability work.
