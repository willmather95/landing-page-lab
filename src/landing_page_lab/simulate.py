"""Simulated traffic with KNOWN true conversion rates.

Used by the demo and by the calibration tests: if the readout is honest, it should call
the true best arm most of the time, and almost never call a winner when every arm is
identical. Everything here is SIMULATED. No real visitors are involved.
"""

from __future__ import annotations

import csv
import io
import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from .readout import Policy, Readout, Status, readout
from .stats import ArmCounts, two_proportion_ztest

# Monday..Sunday. Traffic dips at the weekend and weekend visitors convert a bit less.
WEEKDAY_TRAFFIC = (1.00, 1.06, 1.05, 1.01, 0.93, 0.72, 0.78)
WEEKDAY_CVR = (1.00, 1.03, 1.03, 1.00, 0.95, 0.86, 0.90)


@dataclass(frozen=True)
class TrueArm:
    name: str
    rate: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.rate < 1:
            raise ValueError(f"{self.name}: rate must be in [0, 1)")
        if self.weight <= 0:
            raise ValueError(f"{self.name}: weight must be > 0")


@dataclass(frozen=True)
class DayCount:
    day: int
    arm: str
    visitors: int
    conversions: int


def simulate_traffic(
    arms: Sequence[TrueArm],
    *,
    days: int = 21,
    daily_visitors: int = 2000,
    seed: int = 0,
    actual_weights: Sequence[float] | None = None,
    start_weekday: int = 0,
) -> list[DayCount]:
    """Per-day, per-arm visitors and conversions.

    actual_weights lets a test inject a broken split (sample ratio mismatch) while the
    planned split stays in TrueArm.weight.
    """
    rng = random.Random(seed)
    weights = list(actual_weights) if actual_weights is not None else [a.weight for a in arms]
    if len(weights) != len(arms):
        raise ValueError("one actual weight per arm")
    out: list[DayCount] = []
    for d in range(1, days + 1):
        wd = (start_weekday + d - 1) % 7
        mean = daily_visitors * WEEKDAY_TRAFFIC[wd]
        total = max(0, round(rng.gauss(mean, math.sqrt(mean))))  # Poisson-like day total
        remaining, w_left = total, float(sum(weights))
        for i, arm in enumerate(arms):
            if i == len(arms) - 1:
                n = remaining
            else:
                n = rng.binomialvariate(remaining, min(1.0, weights[i] / w_left)) if remaining else 0
            remaining -= n
            w_left -= weights[i]
            p = min(0.999, arm.rate * WEEKDAY_CVR[wd])
            conv = rng.binomialvariate(n, p) if n else 0
            out.append(DayCount(d, arm.name, n, conv))
    return out


def cumulative(rows: Iterable[DayCount], through_day: int, order: Sequence[str] | None = None) -> list[ArmCounts]:
    vis: dict[str, int] = {}
    conv: dict[str, int] = {}
    for r in rows:
        if r.day <= through_day:
            vis[r.arm] = vis.get(r.arm, 0) + r.visitors
            conv[r.arm] = conv.get(r.arm, 0) + r.conversions
        else:
            vis.setdefault(r.arm, 0)
            conv.setdefault(r.arm, 0)
    names = list(order) if order else list(vis)
    return [ArmCounts(n, vis.get(n, 0), conv.get(n, 0)) for n in names]


def to_csv(rows: Iterable[DayCount]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["day", "variant", "visitors", "conversions"])
    for r in rows:
        w.writerow([r.day, r.arm, r.visitors, r.conversions])
    return buf.getvalue()


def from_csv(text: str) -> list[DayCount]:
    reader = csv.DictReader(io.StringIO(text))
    return [DayCount(int(r["day"]), r["variant"], int(r["visitors"]), int(r["conversions"])) for r in reader]


@dataclass(frozen=True)
class SequentialRun:
    seed: int
    final: Readout
    decision_day: int
    history: tuple[Readout, ...]

    @property
    def winner(self) -> str | None:
        return self.final.winner


def run_sequential(
    arms: Sequence[TrueArm],
    *,
    policy: Policy | None = None,
    daily_visitors: int = 2000,
    seed: int = 0,
    actual_weights: Sequence[float] | None = None,
    detail: bool = False,
    rows: Sequence[DayCount] | None = None,
) -> SequentialRun:
    """Simulate a full experiment and read it at each planned look until a terminal call."""
    policy = policy or Policy()
    days = policy.look_days[-1]
    rows = list(rows) if rows is not None else simulate_traffic(
        arms, days=days, daily_visitors=daily_visitors, seed=seed, actual_weights=actual_weights
    )
    order = [a.name for a in arms]
    history: list[Readout] = []
    for d in policy.look_days:
        r = readout(
            cumulative(rows, d, order), control=order[0], weights=[a.weight for a in arms],
            day=d, policy=policy, detail=detail, seed=seed,
        )
        history.append(r)
        if r.status is not Status.KEEP_RUNNING:
            return SequentialRun(seed, r, d, tuple(history))
    return SequentialRun(seed, history[-1], days, tuple(history))


def naive_peeking_false_call(rows: Sequence[DayCount], order: Sequence[str], alpha: float = 0.05) -> bool:
    """What a dashboard-watcher does: check p < alpha every day and stop at the first hit."""
    days = max(r.day for r in rows)
    for d in range(1, days + 1):
        cum = cumulative(rows, d, order)
        ctrl = cum[0]
        for arm in cum[1:]:
            if arm.visitors and ctrl.visitors and two_proportion_ztest(arm, ctrl).p_value < alpha:
                return True
    return False
