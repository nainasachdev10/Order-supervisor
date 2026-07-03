# Order Supervisor (POC)

A long-running AI supervisor that oversees a single order end-to-end, one Temporal workflow per
order, with event-driven wake/sleep and tool-calling.

## Demo video

Walkthrough: https://www.loom.com/share/8c0310bafcf14cbd8a7f7e663ff75f0e 

## Stack

- **Backend**: Python, FastAPI, `temporalio` (Temporal Python SDK)
- **Frontend**: Next.js (App Router) + Tailwind CSS
- **Persistence**: SQLite by default (via SQLAlchemy async), swappable to Postgres/Supabase with one env var
- **Agent brain**: Claude (Anthropic API) if `ANTHROPIC_API_KEY` is set, otherwise a deterministic
  rule-based engine — the whole system is fully demoable with **zero external API keys**.

## Quick start

You need three things running: a Temporal server, the backend (API + worker), and the frontend.

### 1. Temporal server (dev mode - simplest)

Install the [Temporal CLI](https://docs.temporal.io/cli#install), then:

```bash
temporal server start-dev
```

This starts a local Temporal server on `localhost:7233` with a Web UI at `localhost:8233`.

Alternative: `docker compose up` from the repo root spins up a Postgres-backed Temporal server +
UI (`docker-compose.yml`) if you'd rather not install the CLI.

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or your preferred venv tool
pip install -r requirements.txt
cp .env.example .env      # optionally add ANTHROPIC_API_KEY

# seed one default supervisor template (optional, the UI can also create one)
python -m seed

# terminal A: the Temporal worker (runs workflow + activities)
python -m app.worker

# terminal B: the FastAPI server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`.

### 4. Try it

1. Create (or use the seeded) supervisor template.
2. Start a run with an order ID.
3. Open the run, inject events from the dropdown (`payment_failed`, `shipment_delayed`,
   `delivered`, etc.) and watch the timeline, memory summary, and next-wake-time update.
4. Add a run-specific instruction, pause/resume/terminate, and see it reflected live.
5. Send `delivered` (or `terminate`) to see the final summary/learnings appear.

## Notes on scope decisions

- **SQLite instead of Postgres by default**: purely a local-dev-speed choice. Swap
  `DATABASE_URL` in `backend/.env` to a Postgres/Supabase connection string and nothing else
  changes — the schema is plain SQLAlchemy.
- **Rule-based agent fallback**: lets the whole system run and be demoed without any API key.
  Set `ANTHROPIC_API_KEY` to see the same code path make real LLM-driven decisions instead; the
  workflow/orchestration logic doesn't change either way.
- **Demo-scale timers**: sleep durations in the rule engine are realistic (hours), so for a live
  demo, use the `no_update_for_n_hours` / short-interval paths, or just inject events manually to
  trigger wakes rather than waiting for a real scheduled wake-up. See `ARCHITECTURE.md` for how to
  shorten these if you want to visibly demonstrate a scheduled (timer-based) wake-up.

See `ARCHITECTURE.md` for the design write-up.
