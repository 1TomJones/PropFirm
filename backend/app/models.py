from __future__ import annotations

from pydantic import BaseModel, Field


class StrategyInputs(BaseModel):
    win_rate: float = Field(0.5, ge=0, le=1)
    risk_reward: float = Field(1.0, gt=0)
    risk_per_trade_pct: float = Field(0.01, gt=0, le=1)


class SmartModeInputs(BaseModel):
    enabled: bool = False
    consistency_pct: float = Field(0.5, gt=0, le=1)
    max_trades_per_day: int = Field(5, ge=1, le=200)
    max_days: int = Field(30, ge=1, le=365)
    rr_min: float = Field(0.5, gt=0)
    rr_max: float = Field(4.0, gt=0)
    rr_step: float = Field(0.5, gt=0)
    max_risk_per_trade_pct: float = Field(0.02, gt=0, le=1)


class SimulationRequest(BaseModel):
    initial_balance: float = Field(100000, gt=0)
    success_gain_pct: float = Field(0.1, gt=0)
    fail_loss_pct: float = Field(0.06, gt=0)
    trailing_drawdown_enabled: bool = False
    timeout_trades: int = Field(100, ge=1, le=100000)
    simulations: int = Field(200, ge=1, le=10000)
    store_paths: bool = True
    max_paths_returned: int = Field(200, ge=0, le=5000)
    path_decimation_step: int = Field(1, ge=1, le=1000)
    strategy: StrategyInputs = Field(default_factory=StrategyInputs)
    smart_mode: SmartModeInputs = Field(default_factory=SmartModeInputs)


class SimulationResponse(BaseModel):
    passed: int
    failed: int
    timeout: int
    pass_probability: float
    fail_probability: float
    timeout_probability: float
    sampled_paths: list[list[float]]
    sampled_eod_paths: list[list[float]] = Field(default_factory=list)
    path_outcomes: list[str]
    paths_returned: int
    paths_total: int


class SimulationJobCreateResponse(BaseModel):
    job_id: str


class SimulationJobStatusResponse(BaseModel):
    job_id: str
    status: str
    completed_simulations: int
    total_simulations: int
    result: SimulationResponse | None = None
    error: str | None = None
