# Simple Prop Firm Monte Carlo Simulator

A simplified FastAPI + Chart.js app that runs Monte Carlo simulations with only the core controls:

- Initial balance
- Success target (% gain)
- Fail threshold (% loss)
- Timeout duration (number of trades)
- Number of simulations
- Strategy assumptions (win rate, risk:reward, and risk per trade % of initial balance)

## What it shows

- One line per simulation on an equity-path chart.
- Outcome counts for passed, failed, and timed out simulations.
- A pie chart for passed vs failed vs timed out outcomes.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export REDIS_URL=redis://localhost:6379/0
uvicorn backend.app.main:app --reload --port 8000
```

Run a worker in a second terminal:

```bash
source .venv/bin/activate
export REDIS_URL=redis://localhost:6379/0
python -m backend.app.worker
```

Open `http://localhost:8000`.

## API

- `GET /api/health`
- `GET /api/status` (checks API process and shared durable store connectivity)
- `POST /api/simulate/jobs` (enqueue simulation)
- `GET /api/simulate/jobs/{job_id}` (job status/progress/result from Redis)

## Deployment topology (Render)

The app is split into separate services:

1. **Web service** (`propfirm-dashboard-web`): serves API + static frontend.
2. **Worker service** (`propfirm-dashboard-worker`): background process that consumes queued simulation jobs.
3. **Redis service** (`propfirm-dashboard-redis`): durable shared store for job metadata, progress, queue, and results.

This separation ensures job progress and completed results survive web service restarts, because job state is read from Redis instead of in-memory process state.

## Required environment variables

- `REDIS_URL` (recommended in production): Redis connection string used by both web and worker services.
- `PYTHON_VERSION` (Render-managed in `render.yaml`): Python runtime version.

If `REDIS_URL` is not set, the web app now falls back to an in-memory job store and runs jobs in-process. This keeps the app bootable, but queued jobs and progress state are not durable across restarts and horizontal scaling.
