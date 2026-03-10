# Simple Prop Firm Monte Carlo Simulator

A simplified FastAPI + Chart.js app that runs Monte Carlo simulations with only the core controls:

- Initial balance
- Success target (% gain)
- Fail threshold (% loss)
- Timeout duration (number of trades)
- Number of simulations
- Strategy assumptions (win rate and risk:reward)

## What it shows

- One line per simulation on an equity-path chart.
- Outcome counts for passed, failed, and timed out simulations.
- A pie chart for passed vs failed vs timed out outcomes.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## API

- `GET /api/health`
- `POST /api/simulate`
