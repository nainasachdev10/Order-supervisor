import asyncio
import concurrent.futures

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TASK_QUEUE
from app.workflows import OrderSupervisorWorkflow
from app.activities import (
    classify_events_activity,
    agent_decide_activity,
    execute_tool_activity,
    generate_final_summary_activity,
    sync_run_state_activity,
)


async def main():
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[OrderSupervisorWorkflow],
            activities=[
                classify_events_activity,
                agent_decide_activity,
                execute_tool_activity,
                generate_final_summary_activity,
                sync_run_state_activity,
            ],
            activity_executor=activity_executor,
        )
        print(f"Worker started. Task queue: {TASK_QUEUE}, namespace: {TEMPORAL_NAMESPACE}")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
