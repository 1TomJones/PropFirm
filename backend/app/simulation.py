from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .models import SimulationRequest, SimulationResponse


ProgressCallback = Callable[[int, int], None]


def _simulate_path(rng: np.random.Generator, request: SimulationRequest) -> tuple[str, list[float]]:
    balance = request.initial_balance
    success_level = request.initial_balance * (1 + request.success_gain_pct)
    fail_level = request.initial_balance * (1 - request.fail_loss_pct)
    path = [balance]

    loss_unit = request.initial_balance * request.strategy.risk_per_trade_pct
    win_unit = loss_unit * request.strategy.risk_reward

    outcome = "timeout"

    for _ in range(request.timeout_trades):
        if outcome != "timeout":
            path.append(balance)
            continue

        if rng.random() < request.strategy.win_rate:
            balance += win_unit
        else:
            balance -= loss_unit

        path.append(balance)

        if balance >= success_level:
            outcome = "passed"
        elif balance <= fail_level:
            outcome = "failed"

    return outcome, path


def run_simulation(
    request: SimulationRequest,
    *,
    chunk_size: int = 100,
    on_progress: ProgressCallback | None = None,
) -> SimulationResponse:
    rng = np.random.default_rng()

    outcomes: list[str] = []
    paths: list[list[float]] = []

    total = request.simulations
    for chunk_start in range(0, total, max(1, chunk_size)):
        chunk_end = min(chunk_start + max(1, chunk_size), total)
        for _ in range(chunk_start, chunk_end):
            outcome, path = _simulate_path(rng, request)
            outcomes.append(outcome)
            paths.append(path)

        if on_progress is not None:
            on_progress(chunk_end, total)

    passed = outcomes.count("passed")
    failed = outcomes.count("failed")
    timeout = outcomes.count("timeout")

    return SimulationResponse(
        passed=passed,
        failed=failed,
        timeout=timeout,
        pass_probability=passed / total,
        fail_probability=failed / total,
        timeout_probability=timeout / total,
        sampled_paths=paths,
        path_outcomes=outcomes,
    )
