from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .models import SimulationRequest, SimulationResponse


ProgressCallback = Callable[[int, int], None]


def _simulate_path(
    rng: np.random.Generator,
    request: SimulationRequest,
    *,
    collect_path: bool,
) -> tuple[str, list[float] | None]:
    balance = request.initial_balance
    success_level = request.initial_balance * (1 + request.success_gain_pct)
    fail_level = request.initial_balance * (1 - request.fail_loss_pct)
    path: list[float] | None = [balance] if collect_path else None

    loss_unit = request.initial_balance * request.strategy.risk_per_trade_pct
    win_unit = loss_unit * request.strategy.risk_reward

    outcome = "timeout"

    for tick in range(1, request.timeout_trades + 1):
        if rng.random() < request.strategy.win_rate:
            balance += win_unit
        else:
            balance -= loss_unit

        if collect_path and (
            tick % request.path_decimation_step == 0 or tick == request.timeout_trades
        ):
            path.append(balance)

        if balance >= success_level:
            outcome = "passed"
            if collect_path and (tick % request.path_decimation_step != 0):
                path.append(balance)
            break
        elif balance <= fail_level:
            outcome = "failed"
            if collect_path and (tick % request.path_decimation_step != 0):
                path.append(balance)
            break

    return outcome, path


def run_simulation(
    request: SimulationRequest,
    *,
    chunk_size: int = 100,
    on_progress: ProgressCallback | None = None,
) -> SimulationResponse:
    rng = np.random.default_rng()

    sampled_outcomes: list[str] = []
    sampled_paths: list[list[float]] = []
    passed = 0
    failed = 0
    timeout = 0

    max_paths = request.max_paths_returned if request.store_paths else 0

    total = request.simulations
    for chunk_start in range(0, total, max(1, chunk_size)):
        chunk_end = min(chunk_start + max(1, chunk_size), total)
        for i in range(chunk_start, chunk_end):
            sampled_index: int | None = None
            if request.store_paths and max_paths > 0:
                if i < max_paths:
                    sampled_index = i
                else:
                    candidate_index = int(rng.integers(0, i + 1))
                    if candidate_index < max_paths:
                        sampled_index = candidate_index

            outcome, path = _simulate_path(
                rng,
                request,
                collect_path=sampled_index is not None,
            )

            if outcome == "passed":
                passed += 1
            elif outcome == "failed":
                failed += 1
            else:
                timeout += 1

            if sampled_index is None or path is None:
                continue

            if sampled_index == len(sampled_paths):
                sampled_paths.append(path)
                sampled_outcomes.append(outcome)
            else:
                sampled_paths[sampled_index] = path
                sampled_outcomes[sampled_index] = outcome

        if on_progress is not None:
            on_progress(chunk_end, total)

    return SimulationResponse(
        passed=passed,
        failed=failed,
        timeout=timeout,
        pass_probability=passed / total,
        fail_probability=failed / total,
        timeout_probability=timeout / total,
        sampled_paths=sampled_paths,
        path_outcomes=sampled_outcomes,
        paths_returned=len(sampled_paths),
        paths_total=total,
    )
