from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TradeModelInputs(BaseModel):
    win_rate: float = Field(0.5, ge=0, le=1)
    rr_ratio: float = Field(1.5, gt=0)
    risk_per_trade_pct: float = Field(0.01, gt=0, le=1)
    risk_model: Literal["percent", "fixed"] = "percent"
    fixed_risk_amount: float = Field(100.0, ge=0)
    trades_per_attempt: int = Field(80, ge=1, le=5000)


class ChallengeInputs(BaseModel):
    initial_balance: float = Field(100000, gt=0)
    pass_threshold_pct: float = Field(0.1, gt=0)
    fail_threshold_pct: float = Field(0.06, gt=0)
    challenge_cost: float = Field(129.0, ge=0)
    payout_if_passed: Optional[float] = Field(default=None, ge=0)
    profit_split_pct: Optional[float] = Field(default=0.8, ge=0, le=1)
    reset_fee: Optional[float] = Field(default=None, ge=0)
    max_daily_loss_pct: Optional[float] = Field(default=None, gt=0)
    trailing_drawdown: bool = False
    static_drawdown: bool = True


class MonteCarloInputs(BaseModel):
    simulations: int = Field(5000, ge=100, le=100000)
    seed: Optional[int] = None
    animated_paths_count: int = Field(100, ge=10, le=500)
    winsorisation: Optional[float] = Field(default=None, ge=0, le=0.25)
    block_resampling: bool = False
    block_size: int = Field(5, ge=1, le=100)
    maximum_attempts: int = Field(40, ge=1, le=1000)


class SimulationRequest(BaseModel):
    trade_model: TradeModelInputs
    challenge: ChallengeInputs
    monte_carlo: MonteCarloInputs


class SummaryMetric(BaseModel):
    label: str
    value: float
    format: Literal["percent", "currency", "number"]


class SimulationResponse(BaseModel):
    pass_probability: float
    fail_probability: float
    unresolved_probability: float
    expected_attempts_to_pass: float
    expected_cost_to_pass: float
    expectancy_ev: float
    average_trades_to_outcome: float
    average_max_drawdown_pct: float
    sharpe_like: float
    mean_ending_equity: float
    median_ending_equity: float
    mean_max_drawdown_pct: float
    p05_ending_equity: float
    p95_ending_equity: float
    outcomes: list[str]
    ending_balances: list[float]
    max_drawdowns_pct: list[float]
    trades_to_outcome: list[int]
    pass_fail_counts: dict[str, int]
    sampled_paths: list[list[float]]
    sampled_path_outcomes: list[str]
    sensitivity: list[dict[str, float]]
    insights: list[str]
    summary_cards: list[SummaryMetric]
