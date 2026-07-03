"""Mocked tools. Each returns a small result dict describing what would have happened.
Real integrations (messaging provider, ticketing system, etc.) would replace the bodies here
without touching the workflow or agent logic."""

from typing import Any


def send_customer_message(args: dict[str, Any]) -> dict[str, Any]:
    message = args.get("message", "")
    return {"status": "sent", "channel": "email(mock)", "message": message}


def create_internal_note(args: dict[str, Any]) -> dict[str, Any]:
    note = args.get("note", "")
    return {"status": "logged", "note": note}


def escalate_issue(args: dict[str, Any]) -> dict[str, Any]:
    reason = args.get("reason", "unspecified")
    return {"status": "escalated", "reason": reason, "queue": "ops-escalations(mock)"}


def mark_order_for_review(args: dict[str, Any]) -> dict[str, Any]:
    reason = args.get("reason", "unspecified")
    return {"status": "flagged_for_review", "reason": reason}


def schedule_next_wakeup(args: dict[str, Any]) -> dict[str, Any]:
    seconds = args.get("seconds")
    return {"status": "scheduled", "seconds": seconds}


def close_workflow(args: dict[str, Any]) -> dict[str, Any]:
    reason = args.get("reason", "completed")
    return {"status": "closed", "reason": reason}


TOOL_REGISTRY = {
    "send_customer_message": send_customer_message,
    "create_internal_note": create_internal_note,
    "escalate_issue": escalate_issue,
    "mark_order_for_review": mark_order_for_review,
    "schedule_next_wakeup": schedule_next_wakeup,
    "close_workflow": close_workflow,
}


def run_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"status": "error", "error": f"unknown tool '{tool_name}'"}
    return fn(args)
