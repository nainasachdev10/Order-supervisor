# Architecture note

## Core model: one workflow per order

Each order gets exactly one `OrderSupervisorWorkflow` instance, addressed by a deterministic
workflow ID (`order-{order_id}`). The workflow is the single source of truth for that order's
supervision state for as long as it runs; it is what "stays alive" between events.

## Three triggers, one code path

The workflow has exactly one place that invokes the agent (`_invoke_agent`), called from three
places:

1. **Workflow start** — establishes a baseline (`trigger="workflow_start"`).
2. **Incoming signal** — `submit_event` / `add_instruction` append to `pending_events`; the main
   loop drains them and, if a lightweight classifier activity says they're important, invokes the
   agent with `trigger="signal"`.
3. **Scheduled wake-up** — `workflow.wait_condition(..., timeout=seconds_until_wake)` times out
   when no signal has arrived by `next_wake_time`, and the agent is invoked with
   `trigger="scheduled_wakeup"`.

This keeps the agent from ever running in a tight loop: the workflow spends nearly all its time
parked in `wait_condition`, and Temporal's durable timers/signals handle "waking up" without any
polling.

## Sleep/wake mechanics

`next_wake_time` is a plain workflow-local datetime computed as `workflow.now() + sleep_seconds`,
where `sleep_seconds` comes from the agent's decision (`None` means "only wake on the next
signal"). `workflow.wait_condition` is given a timeout computed from that time on every loop
iteration, so:

- an incoming signal short-circuits the wait immediately,
- a timeout with no pending events means the scheduled wake-up fired.

Because this all lives in workflow code (not activities), it's fully deterministic and replay-safe
— Temporal can rebuild the whole state by replaying signals/timers, with all actual side effects
(tool calls, LLM calls, DB writes) isolated in activities.

## Importance classification (wake policy)

A separate `classify_events_activity` runs before deciding whether to invoke the full agent. In
this POC it's a small rule set (a fixed "always important" event-type list, otherwise unknown
event types are escalated rather than silently dropped, per the "good-to-have" unknown-event
guidance). It's structured as its own activity specifically so it could be swapped for a cheap LLM
call without touching the workflow.

## Agent brain: pluggable, LLM or rule-based

`app/agent.py` exposes a single `decide(ctx) -> AgentDecision` function used by
`agent_decide_activity`. If `ANTHROPIC_API_KEY` is set, it prompts Claude with the full context
(base instruction, wake-up guidance, available tools, memory, recent timeline, extra instructions)
and expects strict JSON back (reasoning, actions, updated memory, sleep duration, close decision).
If unset — or if the LLM call throws — it falls back to a deterministic rule engine covering every
event type in the spec. This was a deliberate choice under time constraints: it keeps the
orchestration/workflow logic (the part being evaluated) fully demoable and reliable regardless of
API availability, while still supporting real LLM reasoning as a drop-in.

## Memory & timeline

- **Timeline**: append-only list of `{event, agent_decision, tool_call, system}` entries, kept in
  full inside the workflow (small enough for a POC's order lifecycle) and persisted to the
  `timeline_events` table via `sync_run_state_activity` after every agent invocation, so the UI
  never has to query Temporal directly for history.
- **Memory summary**: a single compact string the agent itself rewrites on every invocation
  (`updated_memory` replaces the old value entirely). This is the "context compaction" — rather
  than re-feeding the full timeline to the agent every time, only the last ~20 timeline entries
  plus the rolling summary are passed in `AgentContext.recent_timeline` / `memory_summary`. For a
  production version, `continue_as_new` would additionally be used once history size approaches
  Temporal's limits, carrying forward only the memory summary and open extra instructions.

## Read model vs. write path

The workflow (via Temporal) is the write path: all mutations happen through signals and workflow
logic. FastAPI's read endpoints (`GET /api/runs`, `GET /api/runs/{id}`) read from a plain
SQL table (`runs`, `timeline_events`) instead of querying the workflow directly. Every agent
invocation ends with `sync_run_state_activity` pushing current status/memory/timeline deltas into
that table. This means:

- the UI can list/inspect runs without needing a live Temporal connection on every page load,
- write operations (signals) go straight to Temporal via `get_workflow_handle(...).signal(...)`.

`workflow.query` (`get_state`) also exists on the workflow itself for direct inspection (e.g. via
`tctl`/Temporal UI or future admin tooling), independent of the DB read model.

## Tools

Four-plus mocked tools (`send_customer_message`, `create_internal_note`, `escalate_issue`,
`mark_order_for_review`, `schedule_next_wakeup`, `close_workflow`) live in `app/tools.py` behind a
single `run_tool(name, args)` dispatcher, called from `execute_tool_activity`. Swapping in real
integrations means editing `tools.py` only.

## What I'd add with more time

- A small/cheap-model LLM call for the wake classifier instead of rules.
- `continue_as_new` once timeline length crosses a threshold.
- Workflow-level query exposed directly to the frontend (bypassing the DB) for true real-time
  state without the 3s polling interval currently used in the UI.
- Multiple supervisor templates with per-template tool allowlists enforced at the agent-prompt
  level (currently just informational).
- Structured, versioned agent output validation (retry-on-malformed-JSON) rather than a bare
  `json.loads`.
