# LangGraph Checkpointing

## Runtime Lifecycle

```text
Interviewer generates one question
  -> wait_for_answer interrupt
  -> PostgreSQL checkpoint
  -> HTTP response returns
  -> candidate submits or skips
  -> aupdate_state(answer IDs)
  -> ainvoke(None)
  -> Answer Critic
  -> Plan Reviser
  -> Interviewer
  -> next interrupt or END
```

The candidate can take minutes to answer without holding an HTTP connection or
an LLM request open.

## Runtime Scope

Only the multi-turn interview uses `<interview_id>:runtime`, because it pauses
for human input. Planner and Final Evaluator are one-shot Celery tasks: they use
the same Agent graph without psycopg checkpoints and rely on task timeout,
retry, and persisted business status instead.

## Storage

`langgraph-checkpoint-postgres` creates its official checkpoint tables through
the idempotent `AsyncPostgresSaver.setup()` call. The connection defaults to the
application PostgreSQL database. `postgresql+asyncpg://` is converted to the
psycopg-compatible `postgresql://` scheme.

Set `LANGGRAPH_CHECKPOINT_DATABASE_URL` only when checkpoints should use a
separate PostgreSQL database or credential.

## Recovery Rules

- A repeated answer request resumes the persisted runtime thread.
- A skipped or timed-out question resumes with `question_skipped=true` and goes
  directly back to Interviewer without invoking Critic.
- A missing business question is rebuilt from the checkpointed generated turn.
- Existing in-progress interviews without a checkpoint start from their current
  database question and remain compatible.
- Deleting an interview cleans all related checkpoint threads.

## Remaining Reliability Work

- Add fault-injection and restart recovery tests.
- Add an AgentRun audit table independent of mutable checkpoint internals.
- Add administrative checkpoint inspection and controlled replay APIs.
- Define retention and encrypted-backup policies for checkpoint tables.
