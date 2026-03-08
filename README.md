# Prop Firm Challenge Monte Carlo Dashboard

A full-stack web dashboard for modeling prop firm challenge outcomes with Monte Carlo simulation and a dark quant-style UI.

## Stack
- **Frontend:** Static dashboard UI (HTML/CSS/JS + Chart.js) served by FastAPI
- **Backend:** FastAPI + NumPy simulation engine
- **Deploy:** Render Web Service (`render.yaml` included)

## Features
- Pass/fail probability for prop challenges
- Expected attempts to pass (`≈ 1 / pass_probability`, capped by max attempts)
- Expected cost to pass, including optional reset fee
- EV/expectancy using optional payout + profit split
- Monte Carlo equity paths and outcome distributions
- Histograms for ending equity, max drawdown, and trades-to-outcome
- Pass/fail summary chart and sensitivity heatmap
- Plain-English insights panel
- CSV export for simulation outcomes
- Risk model switch: `% risk` vs fixed-dollar risk

## Local development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Then open: `http://localhost:8000`

## Render deployment

### Option A: Blueprint (recommended)
1. Push repo to GitHub.
2. In Render, create a **Blueprint** for this repo.
3. Render reads `render.yaml` and deploys automatically.

### Option B: Manual web service
- Runtime: Python 3.11
- Build Command:
  ```bash
  python -m pip install --upgrade pip setuptools wheel && pip install -r backend/requirements.txt
  ```
- Start Command:
  ```bash
  uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
  ```


### If build hangs on NumPy
Use these Render settings to avoid source builds:
- **Build Command:**
  ```bash
  python -m pip install --upgrade pip setuptools wheel && pip install -r backend/requirements.txt
  ```
- **Start Command:**
  ```bash
  uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
  ```
- **Python version (native runtime):** `3.11.10` via `runtime.txt` (and `PYTHON_VERSION` in `render.yaml`).

Watch build logs for source-build fallback signals:
- `Downloading numpy-*.tar.gz`
- `Preparing metadata (pyproject.toml): still running...`
- `Building wheel for numpy ...`

Healthy first deploys on free tier usually finish dependency install in a few minutes. If NumPy metadata/build steps run for a long time (for example 10+ minutes with repeated metadata/build output), it usually means Render fell back to building from source instead of using a prebuilt wheel.

Rollback note: if any downstream package in your environment requires NumPy 2.x, revert NumPy pin to the previous value and redeploy after confirming wheel availability for your exact Python/runtime combination.

## API
- `GET /api/health`
- `POST /api/simulate`
- `POST /api/export/csv`

Simulation payload schema is in `backend/app/models.py`.

## Modeling assumptions
- Each trade is Bernoulli win/loss from win rate.
- Win PnL = `risk * RR`; loss PnL = `-risk`.
- Attempts end on pass threshold, fail threshold, or max trades.
- Supports static drawdown and optional trailing drawdown.
- EV formula: `(pass_prob * payout_if_passed * profit_split) - expected_cost_to_pass`.
- This is a probabilistic analytics tool, not broker-grade execution software.
