import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./order_supervisor.db")
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.getenv("TASK_QUEUE", "order-supervisor-tq")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # optional - falls back to rule engine if unset
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Demo speed knobs - real deployments would use hours, we compress for demoability
DEMO_TIME_SCALE_SECONDS = int(os.getenv("DEMO_TIME_SCALE_SECONDS", "1"))  # 1 "hour" of wake-up = this many real seconds
