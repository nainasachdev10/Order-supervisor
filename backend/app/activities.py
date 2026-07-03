import datetime
import json
from typing import Any

from temporalio import activity

from app.agent import decide as agent_decide
from app.schemas import AgentContext, AgentDecision, ToolAction
from app.tools import run_tool

# Events that always wake the main agent regardless of what a classifier thinks.
ALWAYS_IMPORTANT = {
    "payment_failed",
    "shipment_delayed",
    "refund_requested",
    "delivered",
    "customer_message_received",
}
# Events that are logged but usually don't need to wake the full agent on their own.
USUALLY_MINOR = {"no_update_for_n_hours"}


@activity.defn
async def classify_events_activity(events: list[dict[str, Any]]) -> bool:
    """Lightweight policy/classifier: should these events wake the main agent right now?
    A simple implementation is acceptable per the brief - this is intentionally cheap and fast,
    a real version could be a small/cheap LLM call instead of pure rules."""
    for e in events:
        et = e.get("event_type")
        if et in ALWAYS_IMPORTANT:
            return True
        if et not in USUALLY_MINOR:
            # unknown event types are escalated (wake the agent) rather than silently dropped
            return True
    return False


@activity.defn
async def agent_decide_activity(ctx_dict: dict[str, Any]) -> dict[str, Any]:
    ctx = AgentContext(**ctx_dict)
    decision: AgentDecision = agent_decide(ctx)
    return decision.model_dump()


@activity.defn
async def execute_tool_activity(action: dict[str, Any]) -> dict[str, Any]:
    act = ToolAction(**action)
    result = run_tool(act.tool, act.args)
    return {"tool": act.tool, "args": act.args, "reasoning": act.reasoning, "result": result}


@activity.defn
async def generate_final_summary_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Produces the end-of-run output: summary, key actions, learnings, recommendations.
    Reuses the same agent brain (LLM or rule-based) with a summarization-flavored prompt when an
    LLM is configured; otherwise builds a structured summary directly from the timeline."""
    from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

    order_id = payload["order_id"]
    memory = payload["memory_summary"]
    timeline = payload["timeline"]
    close_reason = payload.get("close_reason") or "workflow ended"

    action_events = [t for t in timeline if t.get("type") == "tool_call"]
    key_actions = [
        f"{a['payload']['tool']}: {a['payload'].get('result', {}).get('status', 'done')}"
        for a in action_events
    ]

    if ANTHROPIC_API_KEY:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            system = (
                "You write end-of-run reports for an AI order supervision system. Given the memory "
                "summary and timeline of an order run, respond with ONLY JSON: "
                '{"summary": str, "key_actions": [str], "learnings": [str], "recommendations": [str]}'
            )
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=800,
                system=system,
                messages=[{"role": "user", "content": json.dumps({
                    "order_id": order_id, "memory_summary": memory, "timeline": timeline,
                    "close_reason": close_reason,
                })}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except Exception as e:  # noqa: BLE001
            pass  # fall through to template-based summary below

    return {
        "summary": f"Order {order_id} supervision ended ({close_reason}). {memory}",
        "key_actions": key_actions or ["No tool actions were taken during this run."],
        "learnings": [
            "Event-driven wake/sleep kept the agent from polling continuously.",
            f"{len(timeline)} timeline entries were recorded across the run.",
        ],
        "recommendations": [
            "Review escalations flagged during this run for follow-up.",
            "Consider tuning wake-up guidance if the agent woke more/less often than desired.",
        ],
    }


# ---- DB sync activities (the read-model FastAPI/Next.js query) ----

@activity.defn
async def sync_run_state_activity(state: dict[str, Any]) -> None:
    """Upserts the run row and appends any new timeline entries. Runs inside an activity so it can
    freely use async DB I/O (not allowed directly in deterministic workflow code)."""
    from app.db import SessionLocal
    from app.models import Run, TimelineEvent
    from sqlalchemy import select

    async with SessionLocal() as session:
        result = await session.execute(select(Run).where(Run.id == state["run_id"]))
        run = result.scalar_one_or_none()
        if run is None:
            return
        run.status = state["status"]
        run.next_wake_time = (
            datetime.datetime.fromisoformat(state["next_wake_time"]) if state.get("next_wake_time") else None
        )
        run.memory_summary = state["memory_summary"]
        run.extra_instructions = state["extra_instructions"]
        run.final_summary = state.get("final_summary")
        run.updated_at = datetime.datetime.utcnow()

        for entry in state.get("new_timeline_entries", []):
            session.add(TimelineEvent(
                run_id=state["run_id"],
                type=entry["type"],
                payload=entry["payload"],
                important=entry.get("important", True),
            ))
        await session.commit()
