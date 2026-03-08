from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .models import ChallengeInputs, MonteCarloInputs, SimulationRequest, SimulationResponse, SummaryMetric, TradeModelInputs


@dataclass
class AttemptResult:
    outcome: str
    ending_balance: float
    max_drawdown_pct: float
    trades_taken: int
    path: list[float]


def _calculate_risk_amount(balance: float, trade_model: TradeModelInputs, initial_balance: float) -> float:
    if trade_model.risk_model == "fixed":
        return trade_model.fixed_risk_amount
    return balance * trade_model.risk_per_trade_pct


def _simulate_single_attempt(
    rng: np.random.Generator,
    trade_model: TradeModelInputs,
    challenge: ChallengeInputs,
) -> AttemptResult:
    initial_balance = challenge.initial_balance
    pass_level = initial_balance * (1 + challenge.pass_threshold_pct)
    static_fail_level = initial_balance * (1 - challenge.fail_threshold_pct)

    balance = initial_balance
    peak_balance = initial_balance
    trail_fail_level = static_fail_level
    max_drawdown_pct = 0.0
    day_pnl = 0.0
    path = [balance]

    for trade_idx in range(1, trade_model.trades_per_attempt + 1):
        risk_amount = _calculate_risk_amount(balance, trade_model, initial_balance)
        is_win = rng.random() < trade_model.win_rate
        pnl = risk_amount * trade_model.rr_ratio if is_win else -risk_amount

        if challenge.max_daily_loss_pct:
            day_pnl += pnl
            if day_pnl <= -(challenge.max_daily_loss_pct * initial_balance):
                balance += pnl
                path.append(balance)
                dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0.0
                max_drawdown_pct = max(max_drawdown_pct, dd)
                return AttemptResult("failed", balance, max_drawdown_pct, trade_idx, path)

        balance += pnl
        peak_balance = max(peak_balance, balance)
        if challenge.trailing_drawdown:
            trail_fail_level = max(trail_fail_level, peak_balance * (1 - challenge.fail_threshold_pct))

        drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown)
        path.append(balance)

        fail_level = trail_fail_level if challenge.trailing_drawdown else static_fail_level

        if balance >= pass_level:
            return AttemptResult("passed", balance, max_drawdown_pct, trade_idx, path)
        if challenge.static_drawdown and balance <= static_fail_level:
            return AttemptResult("failed", balance, max_drawdown_pct, trade_idx, path)
        if challenge.trailing_drawdown and balance <= fail_level:
            return AttemptResult("failed", balance, max_drawdown_pct, trade_idx, path)

    return AttemptResult("timeout", balance, max_drawdown_pct, trade_model.trades_per_attempt, path)


def _winsorise(values: np.ndarray, limits: float) -> np.ndarray:
    lower = np.quantile(values, limits)
    upper = np.quantile(values, 1 - limits)
    return np.clip(values, lower, upper)


def _run_sensitivity_grid(base_request: SimulationRequest, pass_prob_model: float) -> list[dict[str, float]]:
    win_rates = np.linspace(max(0.2, base_request.trade_model.win_rate - 0.15), min(0.85, base_request.trade_model.win_rate + 0.15), 7)
    rr_values = np.linspace(max(0.6, base_request.trade_model.rr_ratio - 0.8), base_request.trade_model.rr_ratio + 0.8, 7)

    cells: list[dict[str, float]] = []
    for w in win_rates:
        for rr in rr_values:
            expectancy_edge = (w * rr) - (1 - w)
            adjusted_prob = np.clip(pass_prob_model + expectancy_edge * 0.12, 0.01, 0.99)
            cells.append({"winRate": float(w), "rr": float(rr), "passProbability": float(adjusted_prob)})
    return cells


def _insights(pass_prob: float, exp_attempts: float, exp_cost: float, avg_trades: float, request: SimulationRequest) -> list[str]:
    challenge_fee = request.challenge.challenge_cost
    sensitivity = "highly" if request.trade_model.win_rate < 0.5 else "moderately"
    return [
        f"At these inputs, the strategy passes the challenge in {pass_prob * 100:.1f}% of simulations.",
        f"The expected number of attempts to achieve one pass is {exp_attempts:.2f}.",
        f"At a challenge fee of ${challenge_fee:,.0f}, the expected cost to secure one pass is approximately ${exp_cost:,.0f}.",
        f"Most outcomes resolve within about {avg_trades:.1f} trades.",
        f"Your model appears {sensitivity} sensitive to win rate and RR changes around these assumptions.",
    ]


def run_simulation(request: SimulationRequest) -> SimulationResponse:
    rng = np.random.default_rng(request.monte_carlo.seed)
    mc = request.monte_carlo

    outcomes: list[str] = []
    balances: list[float] = []
    drawdowns: list[float] = []
    trades: list[int] = []
    paths: list[list[float]] = []

    for _ in range(mc.simulations):
        result = _simulate_single_attempt(rng, request.trade_model, request.challenge)
        outcomes.append(result.outcome)
        balances.append(result.ending_balance)
        drawdowns.append(result.max_drawdown_pct)
        trades.append(result.trades_taken)
        paths.append(result.path)

    balances_arr = np.array(balances)
    if mc.winsorisation:
        balances_arr = _winsorise(balances_arr, mc.winsorisation)

    pass_count = outcomes.count("passed")
    fail_count = outcomes.count("failed")
    timeout_count = outcomes.count("timeout")

    pass_prob = pass_count / mc.simulations
    fail_prob = fail_count / mc.simulations
    unresolved = timeout_count / mc.simulations

    effective_pass_prob = max(pass_prob, 1e-9)
    expected_attempts = min(1.0 / effective_pass_prob, float(mc.maximum_attempts))

    per_attempt_cost = request.challenge.challenge_cost
    if request.challenge.reset_fee is not None:
        per_attempt_cost += request.challenge.reset_fee
    expected_cost_to_pass = expected_attempts * per_attempt_cost

    payout = request.challenge.payout_if_passed or 0
    split = request.challenge.profit_split_pct or 0
    expectancy_ev = (pass_prob * payout * split) - expected_cost_to_pass

    returns = np.diff(np.array(paths[0])) / request.challenge.initial_balance if paths and len(paths[0]) > 1 else np.array([0])
    sharpe_like = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252))

    sample_size = min(mc.animated_paths_count, len(paths))
    sampled_idx = rng.choice(len(paths), size=sample_size, replace=False)
    sampled_paths = [paths[i] for i in sampled_idx]
    sampled_outcomes = [outcomes[i] for i in sampled_idx]

    summary_cards = [
        SummaryMetric(label="Pass Probability", value=pass_prob, format="percent"),
        SummaryMetric(label="Fail Probability", value=fail_prob, format="percent"),
        SummaryMetric(label="Expected Attempts", value=expected_attempts, format="number"),
        SummaryMetric(label="Expected Cost to Pass", value=expected_cost_to_pass, format="currency"),
        SummaryMetric(label="Expectancy / EV", value=expectancy_ev, format="currency"),
        SummaryMetric(label="Avg Trades to Outcome", value=float(np.mean(trades)), format="number"),
        SummaryMetric(label="Avg Max Drawdown", value=float(np.mean(drawdowns)), format="percent"),
        SummaryMetric(label="Sharpe-like", value=sharpe_like, format="number"),
        SummaryMetric(label="Mean Ending Equity", value=float(np.mean(balances_arr)), format="currency"),
    ]

    return SimulationResponse(
        pass_probability=pass_prob,
        fail_probability=fail_prob,
        unresolved_probability=unresolved,
        expected_attempts_to_pass=expected_attempts,
        expected_cost_to_pass=expected_cost_to_pass,
        expectancy_ev=expectancy_ev,
        average_trades_to_outcome=float(np.mean(trades)),
        average_max_drawdown_pct=float(np.mean(drawdowns)),
        sharpe_like=sharpe_like,
        mean_ending_equity=float(np.mean(balances_arr)),
        median_ending_equity=float(np.median(balances_arr)),
        mean_max_drawdown_pct=float(np.mean(drawdowns)),
        p05_ending_equity=float(np.quantile(balances_arr, 0.05)),
        p95_ending_equity=float(np.quantile(balances_arr, 0.95)),
        outcomes=outcomes,
        ending_balances=list(balances_arr),
        max_drawdowns_pct=drawdowns,
        trades_to_outcome=trades,
        pass_fail_counts={"passed": pass_count, "failed": fail_count, "timeout": timeout_count},
        sampled_paths=sampled_paths,
        sampled_path_outcomes=sampled_outcomes,
        sensitivity=_run_sensitivity_grid(request, pass_prob),
        insights=_insights(pass_prob, expected_attempts, expected_cost_to_pass, float(np.mean(trades)), request),
        summary_cards=summary_cards,
    )


def response_to_csv_rows(response: SimulationResponse) -> Iterable[str]:
    yield "simulation,outcome,ending_balance,max_drawdown_pct,trades_to_outcome"
    for idx, outcome in enumerate(response.outcomes):
        yield (
            f"{idx + 1},{outcome},{response.ending_balances[idx]:.2f},"
            f"{response.max_drawdowns_pct[idx]:.6f},{response.trades_to_outcome[idx]}"
        )
