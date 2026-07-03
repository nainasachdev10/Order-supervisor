import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.activities import (
        classify_events_activity,
        agent_decide_activity,
        execute_tool_activity,
        generate_final_summary_activity,
        sync_run_state_activity,
    )

DEFAULT_ACTIVITY_TIMEOUT = datetime.timedelta(seconds=30)
RETRY_POLICY = RetryPolicy(maximum_attempts=3)


@dataclass
class RunWorkflowInput:
    run_id: str
    order_id: str
    supervisor_id: str
    base_instruction: str
    wake_up_guidance: str
    tools: list[str]
    model_config_json: dict[str, Any]
    order_context: dict[str, Any] = field(default_factory=dict)


@workflow.defn
class OrderSupervisorWorkflow:
    def __init__(self) -> None:
        self.status = "active"  # active | paused | closed | terminated
        self.paused = False
        self.terminal = False
        self.timeline: list[dict[str, Any]] = []
        self.memory_summary = ""
        self.extra_instructions: list[str] = []
        self.next_wake_time: Optional[datetime.datetime] = None
        self.pending_events: list[dict[str, Any]] = []
        self.final_summary: Optional[dict[str, Any]] = None
        self._input: Optional[RunWorkflowInput] = None

    # ---------------- signals ----------------

    @workflow.signal
    async def submit_event(self, event: dict[str, Any]) -> None:
        self.pending_events.append(event)

    @workflow.signal
    async def add_instruction(self, instruction: str) -> None:
        self.extra_instructions.append(instruction)
        # treat a new instruction as a pseudo-event so the agent reconsiders promptly
        self.pending_events.append({"event_type": "instruction_added", "payload": {"instruction": instruction}})

    @workflow.signal
    async def interrupt(self) -> None:
        self.paused = True
        self.status = "paused"

    @workflow.signal
    async def resume(self) -> None:
        self.paused = False
        self.status = "active"

    @workflow.signal
    async def terminate(self, reason: str) -> None:
        self.terminal = True
        self._terminate_reason = reason

    # ---------------- queries ----------------

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "memory_summary": self.memory_summary,
            "extra_instructions": self.extra_instructions,
            "next_wake_time": self.next_wake_time.isoformat() if self.next_wake_time else None,
            "timeline_length": len(self.timeline),
            "final_summary": self.final_summary,
        }

    # ---------------- main run loop ----------------

    @workflow.run
    async def run(self, wf_input: RunWorkflowInput) -> dict[str, Any]:
        self._input = wf_input
        self._terminate_reason = "terminated"

        await self._invoke_agent(trigger="workflow_start", events=[])

        while not self.terminal:
            timeout = self._seconds_until_wake()
            try:
                await workflow.wait_condition(
                    lambda: self.terminal or len(self.pending_events) > 0,
                    timeout=timeout,
                )
            except TimeoutError:
                pass  # scheduled wake-up reached

            if self.terminal:
                break

            if self.paused:
                # while paused, drain/hold events but do not invoke the agent
                await workflow.wait_condition(lambda: not self.paused or self.terminal)
                continue

            if self.pending_events:
                events = self.pending_events
                self.pending_events = []
                important = await workflow.execute_activity(
                    classify_events_activity, events,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT, retry_policy=RETRY_POLICY,
                )
                for e in events:
                    self.timeline.append({"type": "event", "payload": e, "important": important})
                if important:
                    await self._invoke_agent(trigger="signal", events=events)
                else:
                    await self._sync_state(new_entries=[
                        {"type": "event", "payload": e, "important": False} for e in events
                    ])
            else:
                # woke on schedule with nothing pending
                await self._invoke_agent(trigger="scheduled_wakeup", events=[])

        if self.status not in ("closed",):
            self.status = "terminated"
        await self._finalize()
        return self.final_summary or {}

    # ---------------- helpers ----------------

    def _seconds_until_wake(self) -> Optional[float]:
        if self.next_wake_time is None:
            return None
        delta = (self.next_wake_time - workflow.now()).total_seconds()
        return max(delta, 0)

    async def _invoke_agent(self, trigger: str, events: list[dict[str, Any]]) -> None:
        assert self._input is not None
        ctx = {
            "order_id": self._input.order_id,
            "base_instruction": self._input.base_instruction,
            "wake_up_guidance": self._input.wake_up_guidance,
            "tools": self._input.tools,
            "memory_summary": self.memory_summary,
            "extra_instructions": self.extra_instructions,
            "recent_timeline": self.timeline[-20:],
            "trigger": trigger,
            "triggering_events": events,
            "order_context": self._input.order_context,
            "model_config_json": self._input.model_config_json,
        }
        decision = await workflow.execute_activity(
            agent_decide_activity, ctx,
            start_to_close_timeout=datetime.timedelta(seconds=60), retry_policy=RETRY_POLICY,
        )

        new_entries = [{"type": "agent_decision", "payload": {
            "trigger": trigger, "reasoning": decision["reasoning"],
        }, "important": True}]
        self.timeline.append(new_entries[0])

        for action in decision["actions"]:
            result = await workflow.execute_activity(
                execute_tool_activity, action,
                start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT, retry_policy=RETRY_POLICY,
            )
            entry = {"type": "tool_call", "payload": result, "important": True}
            self.timeline.append(entry)
            new_entries.append(entry)

        self.memory_summary = decision["updated_memory"]

        sleep_seconds = decision.get("sleep_seconds")
        self.next_wake_time = workflow.now() + datetime.timedelta(seconds=sleep_seconds) if sleep_seconds else None

        if decision.get("should_close"):
            self.terminal = True
            self.status = "closed"
            self._close_reason = decision.get("close_reason") or "agent decided order is complete"

        await self._sync_state(new_entries=new_entries)

    async def _sync_state(self, new_entries: list[dict[str, Any]]) -> None:
        state = {
            "run_id": self._input.run_id,
            "status": self.status,
            "next_wake_time": self.next_wake_time.isoformat() if self.next_wake_time else None,
            "memory_summary": self.memory_summary,
            "extra_instructions": self.extra_instructions,
            "final_summary": self.final_summary,
            "new_timeline_entries": new_entries,
        }
        await workflow.execute_activity(
            sync_run_state_activity, state,
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT, retry_policy=RETRY_POLICY,
        )

    async def _finalize(self) -> None:
        close_reason = getattr(self, "_close_reason", None) or getattr(self, "_terminate_reason", "ended")
        payload = {
            "order_id": self._input.order_id,
            "memory_summary": self.memory_summary,
            "timeline": self.timeline,
            "close_reason": close_reason,
        }
        summary = await workflow.execute_activity(
            generate_final_summary_activity, payload,
            start_to_close_timeout=datetime.timedelta(seconds=60), retry_policy=RETRY_POLICY,
        )
        self.final_summary = summary
        await self._sync_state(new_entries=[{"type": "system", "payload": {"event": "run_finalized", "close_reason": close_reason}, "important": True}])
