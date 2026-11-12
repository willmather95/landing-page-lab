"""Calibration: does the readout recover known truths across many seeds? (SIMULATED)"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from .readout import Policy, Status
from .simulate import TrueArm, naive_peeking_false_call, run_sequential, simulate_traffic

WEIGHTS = (34.0, 33.0, 33.0)


@dataclass(frozen=True)
class Scenario:
    name: str
    rates: tuple[float, ...]
    best: str | None              # the arm that should win, or None when no arm is truly better
    actual_weights: tuple[float, ...] | None = None


SCENARIOS = (
    Scenario("A/A/A: all 4.0%", (0.04, 0.04, 0.04), None),
    Scenario("c is +20%", (0.04, 0.04, 0.048), "c"),
    Scenario("demo truth: b +5%, c +20%", (0.04, 0.042, 0.048), "c"),
    Scenario("c is +10% (underpowered)", (0.04, 0.04, 0.044), "c"),
    Scenario("broken split 37/32/31", (0.04, 0.04, 0.048), "c", (37.0, 32.0, 31.0)),
)


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    seeds: int
    right_winner: float
    wrong_winner: float
    no_winner: float
    srm_stops: float
    mean_decision_day: float | None
    naive_peeking_calls: float | None


def run_scenario(sc: Scenario, seeds: Sequence[int], *, daily_visitors: int = 2000, policy: Policy | None = None,
                 with_naive: bool = False) -> ScenarioResult:
    policy = policy or Policy()
    arms = [TrueArm(n, r, w) for n, r, w in zip("abc", sc.rates, WEIGHTS)]
    right = wrong = none = srm = naive = 0
    days: list[int] = []
    for s in seeds:
        rows = simulate_traffic(arms, days=policy.look_days[-1], daily_visitors=daily_visitors, seed=s,
                                actual_weights=sc.actual_weights)
        run = run_sequential(arms, policy=policy, rows=rows)
        st = run.final.status
        if st is Status.WINNER:
            days.append(run.decision_day)
            if sc.best is not None and run.winner == sc.best:
                right += 1
            else:
                wrong += 1
        elif st is Status.INVALID_SRM:
            srm += 1
        else:
            none += 1
        if with_naive:
            naive += naive_peeking_false_call(rows, "abc")
    n = len(seeds)
    return ScenarioResult(sc, n, right / n, wrong / n, none / n, srm / n,
                          sum(days) / len(days) if days else None, naive / n if with_naive else None)


def calibrate(seeds: int = 300, start: int = 1000) -> tuple[list[ScenarioResult], float]:
    t = time.time()
    rng = range(start, start + seeds)
    out = [run_scenario(sc, rng, with_naive=sc.best is None) for sc in SCENARIOS]
    return out, time.time() - t


def to_markdown(results: list[ScenarioResult], seconds: float) -> str:
    n = results[0].seeds if results else 0
    lines = [
        "# Calibration (SIMULATED)",
        "",
        f"{n} seeds per scenario, 2,000 visitors a day before weekday swings, 3 arms split 34/33/33, looks on days 7, 14, 21.",
        "Default policy: P(best) >= 95%, expected loss <= 1% of control, O'Brien-Fleming boundaries, alpha 0.05 split over 2 comparisons.",
        "",
        "| Scenario | Right winner | Wrong winner | No winner | SRM stop | Mean call day |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        day = "" if r.mean_decision_day is None else f"{r.mean_decision_day:.1f}"
        lines.append(f"| {r.scenario.name} | {r.right_winner:.1%} | {r.wrong_winner:.1%} | {r.no_winner:.1%} | {r.srm_stops:.1%} | {day} |")
    for r in results:
        if r.naive_peeking_calls is not None:
            lines += ["", f"Same A/A/A traffic, read the naive way (stop the first day any p < 0.05): "
                          f"**{r.naive_peeking_calls:.1%}** of runs call a false winner, vs **{r.wrong_winner:.1%}** with this readout."]
    lines += ["", f"Runtime: {seconds:.0f}s. Reproduce: `lpl calibrate --seeds {n}`.", ""]
    return "\n".join(lines)
