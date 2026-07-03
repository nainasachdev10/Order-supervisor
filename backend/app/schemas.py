import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- Supervisor config ----

class SupervisorCreate(BaseModel):
    name: str
    base_instruction: str
    tools: list[str] = Field(default_factory=lambda: [
        "send_customer_message",
        "create_internal_note",
        "escalate_issue",
        "mark_order_for_review",
        "schedule_next_wakeup",
        "close_workflow",
    ])
    wake_up_guidance: str = ""
    model_config_json: dict[str, Any] = Field(default_factory=dict)


class SupervisorOut(SupervisorCreate):
    id: str
    created_at: datetime.datetime


# ---- Run lifecycle ----

class RunCreate(BaseModel):
    order_id: str
    supervisor_id: str
    order_context: dict[str, Any] = Field(default_factory=dict)
    base_instruction_override: Optional[str] = None


class RunOut(BaseModel):
    id: str
    order_id: str
    supervisor_id: str
    workflow_id: str
    status: str
    next_wake_time: Optional[datetime.datetime]
    memory_summary: str
    extra_instructions: list[str]
    final_summary: Optional[dict[str, Any]]
    order_context: dict[str, Any]
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    type: str
    payload: dict[str, Any]
    important: bool
    created_at: datetime.datetime


class RunDetailOut(RunOut):
    timeline: list[TimelineEventOut]


# ---- Signals sent into the workflow ----

class OrderEvent(BaseModel):
    """A single event delivered into the workflow as a signal."""
    event_type: str  # e.g. payment_confirmed, shipment_delayed, refund_requested...
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "event_generator"


class InstructionIn(BaseModel):
    instruction: str


class TerminateIn(BaseModel):
    reason: str = "manually terminated by user"


# ---- Internal types passed between workflow <-> activities (must stay JSON-serializable) ----

class AgentContext(BaseModel):
    order_id: str
    base_instruction: str
    wake_up_guidance: str
    tools: list[str]
    memory_summary: str
    extra_instructions: list[str]
    recent_timeline: list[dict[str, Any]]
    trigger: str  # workflow_start | signal | scheduled_wakeup
    triggering_events: list[dict[str, Any]] = Field(default_factory=list)
    order_context: dict[str, Any] = Field(default_factory=dict)
    model_config_json: dict[str, Any] = Field(default_factory=dict)


class ToolAction(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class AgentDecision(BaseModel):
    reasoning: str
    actions: list[ToolAction] = Field(default_factory=list)
    updated_memory: str
    sleep_seconds: Optional[int] = None  # None = sleep indefinitely until next signal
    should_close: bool = False
    close_reason: Optional[str] = None
