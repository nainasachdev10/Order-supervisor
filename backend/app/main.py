import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TASK_QUEUE
from app.db import init_db, get_session
from app.models import Supervisor, Run, TimelineEvent
from app.schemas import (
    SupervisorCreate, SupervisorOut, RunCreate, RunOut, RunDetailOut,
    OrderEvent, InstructionIn, TerminateIn,
)
from app.temporal_client import get_temporal_client
from app.workflows import OrderSupervisorWorkflow, RunWorkflowInput

app = FastAPI(title="Order Supervisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await init_db()


# ---------------- supervisors ----------------

@app.post("/api/supervisors", response_model=SupervisorOut)
async def create_supervisor(body: SupervisorCreate, session: AsyncSession = Depends(get_session)):
    sup = Supervisor(
        name=body.name,
        base_instruction=body.base_instruction,
        tools=body.tools,
        wake_up_guidance=body.wake_up_guidance,
        model_config_json=body.model_config_json,
    )
    session.add(sup)
    await session.commit()
    await session.refresh(sup)
    return sup


@app.get("/api/supervisors", response_model=list[SupervisorOut])
async def list_supervisors(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Supervisor).order_by(Supervisor.created_at.desc()))
    return result.scalars().all()


@app.get("/api/supervisors/{supervisor_id}", response_model=SupervisorOut)
async def get_supervisor(supervisor_id: str, session: AsyncSession = Depends(get_session)):
    sup = await session.get(Supervisor, supervisor_id)
    if not sup:
        raise HTTPException(404, "supervisor not found")
    return sup


# ---------------- runs ----------------

@app.post("/api/runs", response_model=RunOut)
async def create_run(body: RunCreate, session: AsyncSession = Depends(get_session)):
    sup = await session.get(Supervisor, body.supervisor_id)
    if not sup:
        raise HTTPException(404, "supervisor not found")

    workflow_id = f"order-{body.order_id}"
    run = Run(
        order_id=body.order_id,
        supervisor_id=sup.id,
        workflow_id=workflow_id,
        order_context=body.order_context,
        extra_instructions=[],
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    client = await get_temporal_client()
    wf_input = RunWorkflowInput(
        run_id=run.id,
        order_id=body.order_id,
        supervisor_id=sup.id,
        base_instruction=body.base_instruction_override or sup.base_instruction,
        wake_up_guidance=sup.wake_up_guidance,
        tools=sup.tools,
        model_config_json=sup.model_config_json,
        order_context=body.order_context,
    )
    await client.start_workflow(
        OrderSupervisorWorkflow.run,
        wf_input,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return run


@app.get("/api/runs", response_model=list[RunOut])
async def list_runs(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Run).order_by(Run.created_at.desc()))
    return result.scalars().all()


@app.get("/api/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    result = await session.execute(
        select(TimelineEvent).where(TimelineEvent.run_id == run_id).order_by(TimelineEvent.created_at.asc())
    )
    timeline = result.scalars().all()
    return RunDetailOut(**{**run.__dict__, "timeline": timeline})


async def _signal_run(session: AsyncSession, run_id: str, signal_name: str, *args):
    run = await session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    client = await get_temporal_client()
    handle = client.get_workflow_handle(run.workflow_id)
    await handle.signal(signal_name, *args)
    return run


@app.post("/api/runs/{run_id}/events", response_model=RunOut)
async def send_event(run_id: str, event: OrderEvent, session: AsyncSession = Depends(get_session)):
    run = await _signal_run(session, run_id, "submit_event", event.model_dump())
    return run


@app.post("/api/runs/{run_id}/instructions", response_model=RunOut)
async def add_instruction(run_id: str, body: InstructionIn, session: AsyncSession = Depends(get_session)):
    run = await _signal_run(session, run_id, "add_instruction", body.instruction)
    return run


@app.post("/api/runs/{run_id}/interrupt", response_model=RunOut)
async def interrupt_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await _signal_run(session, run_id, "interrupt")
    run.status = "paused"
    await session.commit()
    return run


@app.post("/api/runs/{run_id}/resume", response_model=RunOut)
async def resume_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await _signal_run(session, run_id, "resume")
    run.status = "active"
    await session.commit()
    return run


@app.post("/api/runs/{run_id}/terminate", response_model=RunOut)
async def terminate_run(run_id: str, body: TerminateIn, session: AsyncSession = Depends(get_session)):
    run = await _signal_run(session, run_id, "terminate", body.reason)
    return run


@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}
