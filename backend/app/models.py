import datetime
import uuid

from sqlalchemy import Column, String, DateTime, JSON, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def gen_id() -> str:
    return str(uuid.uuid4())


class Supervisor(Base):
    """A reusable supervisor template: name, base instruction, tools, wake-up guidance, model config."""

    __tablename__ = "supervisors"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    base_instruction = Column(Text, nullable=False)
    tools = Column(JSON, default=list)  # list of tool names enabled for this supervisor
    wake_up_guidance = Column(Text, default="")  # e.g. "wake aggressively on any payment issue"
    model_config_json = Column(JSON, default=dict)  # e.g. {"model": "claude-sonnet-4-6", "temperature": 0.2}
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Run(Base):
    """One run == one Temporal workflow == one order under supervision. This table is the read-model
    the FastAPI/Next.js layer queries; the workflow itself is the write-path source of truth and
    pushes updates here via the `sync_run_state` activity after every agent invocation."""

    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=gen_id)
    order_id = Column(String, nullable=False)
    supervisor_id = Column(String, nullable=False)
    workflow_id = Column(String, nullable=False, unique=True)

    status = Column(String, default="active")  # active | paused | closed | terminated
    next_wake_time = Column(DateTime, nullable=True)
    memory_summary = Column(Text, default="")
    extra_instructions = Column(JSON, default=list)  # list[str]
    final_summary = Column(JSON, nullable=True)
    order_context = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class TimelineEvent(Base):
    """Append-only log of everything that happened in a run: incoming events, agent reasoning,
    tool calls/results, sleep/wake transitions. This is the audit trail shown in the UI."""

    __tablename__ = "timeline_events"

    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)  # event | agent_decision | tool_call | sleep | wake | instruction | system
    payload = Column(JSON, default=dict)
    important = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
