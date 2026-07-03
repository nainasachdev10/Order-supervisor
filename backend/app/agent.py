import json

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.schemas import AgentContext, AgentDecision, ToolAction

SYSTEM_PROMPT_TEMPLATE = """You are an AI order supervisor agent overseeing a single e-commerce order end-to-end.

Base instruction from your operator: {base_instruction}
Wake-up guidance: {wake_up_guidance}
Available tools: {tools}

You decide what to do given the current situation, then respond with ONLY a JSON object (no markdown, no
preamble) matching exactly this schema:

{{
  "reasoning": "short internal reasoning about the situation",
  "actions": [{{"tool": "<tool name from available tools>", "args": {{}}, "reasoning": "why this action"}}],
  "updated_memory": "a compact rolling summary of everything important so far, replacing the old one",
  "sleep_seconds": <int or null>,
  "should_close": <true|false>,
  "close_reason": "<string or null>"
}}

Rules:
- Only call "close_workflow" / set should_close=true when the order has reached a terminal state
  (delivered & no open issues, or explicitly cancelled/refunded and resolved).
- sleep_seconds is how long until you want to be woken up again on a schedule (e.g. to check on a delayed
  shipment). Use null if you only need to be woken by the next incoming event, not on a timer.
- Keep updated_memory compact (a few sentences) - it replaces your entire memory, so carry forward
  anything still relevant, and drop stale detail.
- Do not invent tools outside the available list.
"""


def _rule_based_decision(ctx: AgentContext) -> AgentDecision:
    """Deterministic fallback brain - no API key required. Good enough to demonstrate the
    orchestration/workflow logic end-to-end."""

    events = ctx.triggering_events
    event_types = [e.get("event_type") for e in events]
    memory = ctx.memory_summary
    actions: list[ToolAction] = []
    sleep_seconds = None
    should_close = False
    close_reason = None
    reasoning_parts = []

    def has(*types):
        return any(t in event_types for t in types)

    if ctx.trigger == "workflow_start":
        reasoning_parts.append("Order run started; establishing baseline monitoring.")
        actions.append(ToolAction(tool="create_internal_note", args={"note": "Supervisor initialized."},
                                   reasoning="Record start of supervision."))
        sleep_seconds = 21600  # check back in 6h if nothing happens
        memory = f"Order {ctx.order_id} supervision started."

    elif has("payment_failed"):
        reasoning_parts.append("Payment failed - needs immediate escalation and customer contact.")
        actions.append(ToolAction(tool="escalate_issue", args={"reason": "payment_failed"},
                                   reasoning="Payment failures need human/billing follow-up."))
        actions.append(ToolAction(tool="send_customer_message",
                                   args={"message": "We noticed a payment issue with your order - please update your payment method."},
                                   reasoning="Keep customer informed and unblock the order."))
        sleep_seconds = 3600
        memory = f"{memory} Payment failed; escalated and messaged customer; awaiting retry."

    elif has("refund_requested"):
        reasoning_parts.append("Refund requested - flag for review and notify internally.")
        actions.append(ToolAction(tool="mark_order_for_review", args={"reason": "refund_requested"},
                                   reasoning="Refunds require review before processing."))
        actions.append(ToolAction(tool="create_internal_note",
                                   args={"note": "Customer requested a refund."},
                                   reasoning="Give ops visibility."))
        sleep_seconds = 7200
        memory = f"{memory} Refund requested; marked for review."

    elif has("shipment_delayed"):
        reasoning_parts.append("Shipment delayed - proactively notify customer and escalate if repeated.")
        actions.append(ToolAction(tool="send_customer_message",
                                   args={"message": "Your shipment is delayed - we're on it and will keep you posted."},
                                   reasoning="Proactive comms reduce support load."))
        actions.append(ToolAction(tool="escalate_issue", args={"reason": "shipment_delayed"},
                                   reasoning="Let logistics ops know."))
        sleep_seconds = 10800
        memory = f"{memory} Shipment delayed; customer notified; monitoring for further delay."

    elif has("customer_message_received"):
        reasoning_parts.append("Customer reached out - create an internal note and check if urgent.")
        actions.append(ToolAction(tool="create_internal_note",
                                   args={"note": "Customer sent a message - needs a response."},
                                   reasoning="Ensure it's tracked."))
        sleep_seconds = 3600
        memory = f"{memory} Customer messaged in; awaiting response."

    elif has("delivered"):
        reasoning_parts.append("Order delivered with no open issues - safe to close out supervision.")
        actions.append(ToolAction(tool="close_workflow", args={"reason": "delivered"},
                                   reasoning="Terminal state reached."))
        should_close = True
        close_reason = "Order delivered successfully."
        memory = f"{memory} Order delivered; closing supervision."

    elif has("no_update_for_n_hours"):
        reasoning_parts.append("No updates for a while - light check-in, no action needed yet.")
        sleep_seconds = 14400
        memory = f"{memory} No recent updates; continuing to monitor."

    elif ctx.trigger == "scheduled_wakeup":
        reasoning_parts.append("Scheduled check-in with no new events - nothing urgent, sleep again.")
        sleep_seconds = 21600
        memory = memory or f"Order {ctx.order_id} nominal, periodic check-ins only."

    else:
        reasoning_parts.append("Unrecognized event - logging and doing a short-interval re-check.")
        actions.append(ToolAction(tool="create_internal_note",
                                   args={"note": f"Unrecognized event(s): {event_types}"},
                                   reasoning="Escalation-of-the-unknown per good-to-have guidance."))
        sleep_seconds = 3600
        memory = f"{memory} Saw unrecognized event(s) {event_types}; flagged."

    if ctx.extra_instructions:
        reasoning_parts.append(f"Applying operator instructions: {ctx.extra_instructions}")

    return AgentDecision(
        reasoning=" ".join(reasoning_parts),
        actions=actions,
        updated_memory=memory.strip(),
        sleep_seconds=sleep_seconds,
        should_close=should_close,
        close_reason=close_reason,
    )


def _llm_decision(ctx: AgentContext) -> AgentDecision:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system = SYSTEM_PROMPT_TEMPLATE.format(
        base_instruction=ctx.base_instruction,
        wake_up_guidance=ctx.wake_up_guidance or "none specified - use judgement",
        tools=", ".join(ctx.tools),
    )
    user_content = json.dumps({
        "order_id": ctx.order_id,
        "order_context": ctx.order_context,
        "trigger": ctx.trigger,
        "triggering_events": ctx.triggering_events,
        "memory_summary": ctx.memory_summary,
        "extra_instructions": ctx.extra_instructions,
        "recent_timeline": ctx.recent_timeline[-15:],
    })

    resp = client.messages.create(
        model=ctx.model_config_json.get("model", ANTHROPIC_MODEL),
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(text)
    return AgentDecision(**data)


def decide(ctx: AgentContext) -> AgentDecision:
    """Entry point used by the Temporal activity. Falls back to the rule engine on any LLM error
    so a flaky/unset API key never breaks the workflow."""
    if ANTHROPIC_API_KEY:
        try:
            return _llm_decision(ctx)
        except Exception as e:  # noqa: BLE001 - deliberate broad fallback for POC robustness
            fallback = _rule_based_decision(ctx)
            fallback.reasoning = f"[LLM call failed ({e}); used rule-based fallback] {fallback.reasoning}"
            return fallback
    return _rule_based_decision(ctx)
