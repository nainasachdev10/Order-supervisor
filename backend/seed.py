"""Run with: python -m seed  (after the backend server has started at least once, or standalone -
it initializes its own DB tables)."""
import asyncio

from app.db import init_db, SessionLocal
from app.models import Supervisor


DEFAULT_TOOLS = [
    "send_customer_message",
    "create_internal_note",
    "escalate_issue",
    "mark_order_for_review",
    "schedule_next_wakeup",
    "close_workflow",
]


async def main():
    await init_db()
    async with SessionLocal() as session:
        sup = Supervisor(
            name="Standard Order Supervisor",
            base_instruction=(
                "Watch this order from creation to delivery. Keep the customer informed of "
                "meaningful status changes, escalate payment or shipment problems promptly, and "
                "close out the run once the order is delivered with no open issues."
            ),
            tools=DEFAULT_TOOLS,
            wake_up_guidance="Wake immediately on payment or shipment problems; otherwise check in every few hours.",
            model_config_json={"model": "claude-sonnet-4-6"},
        )
        session.add(sup)
        await session.commit()
        print(f"Created default supervisor: {sup.id} - {sup.name}")


if __name__ == "__main__":
    asyncio.run(main())
