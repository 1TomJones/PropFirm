from __future__ import annotations

import numpy as np

from .models import SimulationRequest, SimulationResponse


def _simulate_path(rng: np.random.Generator, request: SimulationRequest) -> tuple[str, list[float]]:
    balance = request.initial_balance
    success_level = request.initial_balance * (1 + request.success_gain_pct)
    fail_level = request.initial_balance * (1 - request.fail_loss_pct)
    path = [balance]

    loss_unit = request.initial_balance * 0.01
    win_unit = loss_unit * request.strategy.risk_reward

    for _ in range(request.timeout_trades):
        if rng.random() < request.strategy.win_rate:
            balance += win_unit
        else:
            balance -= loss_unit

        path.append(balance)

        if balance >= success_level:
            return "passed", path
        if balance <= fail_level:
            return "failed", path

    return "timeout", path


def run_simulation(request: SimulationRequest) -> SimulationResponse:
    rng = np.random.default_rng()

    outcomes: list[str] = []
    paths: list[list[float]] = []

    for _ in range(request.simulations):
        outcome, path = _simulate_path(rng, request)
        outcomes.append(outcome)
        paths.append(path)

    passed = outcomes.count("passed")
    failed = outcomes.count("failed")
    timeout = outcomes.count("timeout")
    total = request.simulations

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

