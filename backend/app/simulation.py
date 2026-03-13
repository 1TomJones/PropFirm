from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .models import SimulationRequest, SimulationResponse


ProgressCallback = Callable[[int, int], None]


def _build_rr_candidates(request: SimulationRequest) -> list[float]:
    smart = request.smart_mode
    if smart.rr_step <= 0:
        return [max(0.01, smart.rr_min)]
    start = min(smart.rr_min, smart.rr_max)
    stop = max(smart.rr_min, smart.rr_max)
    count = int(np.floor((stop - start) / smart.rr_step)) + 1
    candidates = [start + i * smart.rr_step for i in range(max(1, count))]
    if candidates[-1] < stop:
        candidates.append(stop)
    return [max(0.01, c) for c in candidates]


def _choose_trade_plan(
    *,
    success_remaining: float,
    loss_buffer: float,
    day_profit_remaining: float,
    initial_balance: float,
    rr_candidates: list[float],
    max_risk_pct: float,
) -> tuple[float, float] | None:
    best: tuple[float, float, float] | None = None

    for rr in rr_candidates:
        wr = 1.0 / (1.0 + rr)
        max_risk = initial_balance * max_risk_pct
        cap_from_loss = max(0.0, loss_buffer)
        cap_from_target = max(0.0, success_remaining / max(rr, 0.01))
        cap_from_day = max(0.0, day_profit_remaining / max(rr, 0.01))
        risk = min(max_risk, cap_from_loss, cap_from_target, cap_from_day)
        if risk <= 0:
            continue

        gain = risk * rr
        ev = wr * gain - (1 - wr) * risk
        score = ev + 0.002 * gain
        if best is None or score > best[0]:
            best = (score, rr, risk)

    if best is None:
        return None
    return best[1], best[2]


def _simulate_path(
    rng: np.random.Generator,
    request: SimulationRequest,
    *,
    collect_path: bool,
) -> tuple[str, list[float] | None, list[float] | None]:
    balance = request.initial_balance
    success_level = request.initial_balance * (1 + request.success_gain_pct)
    initial_fail_level = request.initial_balance * (1 - request.fail_loss_pct)
    fail_level = initial_fail_level
    path: list[float] | None = [balance] if collect_path else None
    eod_path: list[float] | None = [balance] if collect_path else None

    peak_balance = balance
    outcome = "timeout"

    if request.smart_mode.enabled:
        rr_candidates = _build_rr_candidates(request)
        max_days = request.smart_mode.max_days
        max_trades_day = request.smart_mode.max_trades_per_day
        consistency_cap = request.smart_mode.consistency_pct * (success_level - request.initial_balance)

        trades_taken = 0
        for _day in range(max_days):
            day_start_balance = balance
            day_profit_limit = max(0.0, consistency_cap)

            for _trade_idx in range(max_trades_day):
                if trades_taken >= request.timeout_trades:
                    break
                success_remaining = max(0.0, success_level - balance)
                loss_buffer = max(0.0, balance - fail_level)
                daily_profit = balance - day_start_balance
                day_profit_remaining = max(0.0, day_profit_limit - daily_profit)

                plan = _choose_trade_plan(
                    success_remaining=success_remaining,
                    loss_buffer=loss_buffer,
                    day_profit_remaining=day_profit_remaining,
                    initial_balance=request.initial_balance,
                    rr_candidates=rr_candidates,
                    max_risk_pct=request.smart_mode.max_risk_per_trade_pct,
                )
                if plan is None:
                    break

                rr, loss_unit = plan
                win_unit = loss_unit * rr
                win_rate = 1.0 / (1.0 + rr)

                if rng.random() < win_rate:
                    balance += win_unit
                else:
                    balance -= loss_unit
                trades_taken += 1

                if collect_path:
                    path.append(balance)

                if balance >= success_level - 1e-9:
                    balance = min(balance, success_level)
                    outcome = "passed"
                    break
                if balance <= fail_level + 1e-9:
                    balance = max(balance, fail_level)
                    outcome = "failed"
                    break

                if (balance - day_start_balance) >= day_profit_limit - 1e-9:
                    break


            if request.trailing_drawdown_enabled and balance > peak_balance:
                peak_balance = balance
                fail_level = min(
                    request.initial_balance,
                    initial_fail_level + max(0.0, peak_balance - request.initial_balance),
                )

            if collect_path:
                eod_path.append(balance)

            if outcome in {"passed", "failed"}:
                break
            if trades_taken >= request.timeout_trades:
                break
        return outcome, path, eod_path

    loss_unit = request.initial_balance * request.strategy.risk_per_trade_pct
    win_unit = loss_unit * request.strategy.risk_reward

    for tick in range(1, request.timeout_trades + 1):
        if rng.random() < request.strategy.win_rate:
            balance += win_unit
        else:
            balance -= loss_unit

        if collect_path and (
            tick % request.path_decimation_step == 0 or tick == request.timeout_trades
        ):
            path.append(balance)

        if request.trailing_drawdown_enabled and balance > peak_balance:
            peak_balance = balance
            fail_level = min(
                request.initial_balance,
                initial_fail_level + max(0.0, peak_balance - request.initial_balance),
            )

        if balance >= success_level:
            outcome = "passed"
            if collect_path and (tick % request.path_decimation_step != 0):
                path.append(balance)
            break
        if balance <= fail_level:
            outcome = "failed"
            if collect_path and (tick % request.path_decimation_step != 0):
                path.append(balance)
            break

    return outcome, path, eod_path


def run_simulation(
    request: SimulationRequest,
    *,
    chunk_size: int = 100,
    on_progress: ProgressCallback | None = None,
) -> SimulationResponse:
    rng = np.random.default_rng()

    sampled_outcomes: list[str] = []
    sampled_paths: list[list[float]] = []
    sampled_eod_paths: list[list[float]] = []
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

            outcome, path, eod_path = _simulate_path(
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
                sampled_eod_paths.append(eod_path or [])
                sampled_outcomes.append(outcome)
            else:
                sampled_paths[sampled_index] = path
                sampled_eod_paths[sampled_index] = eod_path or []
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
        sampled_eod_paths=sampled_eod_paths,
        path_outcomes=sampled_outcomes,
        paths_returned=len(sampled_paths),
        paths_total=total,
    )
