"""Frequentist side: two-proportion z-tests with group-sequential boundaries.

Peeking at a fixed-horizon p-value every day inflates false positives (a 5% test checked
21 times will "win" far more than 5% of the time). The readout instead decides only at
planned looks and compares |z| with a Lan-DeMets alpha-spending boundary. Boundaries are
computed exactly by recursive numerical integration of the Brownian-motion
representation (Armitage, McPherson and Rowe), not by a lookup table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Sequence

from ._math import norm_cdf, norm_pdf, norm_ppf, norm_sf
from .types import ArmCounts

Spending = Literal["obrien_fleming", "pocock"]


@dataclass(frozen=True)
class ZTest:
    arm: str
    control: str
    diff: float
    relative_lift: float | None
    z: float
    p_value: float
    ci_low: float
    ci_high: float


def two_proportion_ztest(arm: ArmCounts, control: ArmCounts, *, ci_level: float = 0.95) -> ZTest:
    """Pooled-variance z statistic, unpooled (Wald) interval for the difference."""
    if arm.visitors == 0 or control.visitors == 0:
        return ZTest(arm.name, control.name, 0.0, None, 0.0, 1.0, -math.inf, math.inf)
    p1, p0 = arm.rate, control.rate
    n1, n0 = arm.visitors, control.visitors
    pooled = (arm.conversions + control.conversions) / (n1 + n0)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n0))
    diff = p1 - p0
    z = diff / se_pooled if se_pooled > 0 else 0.0
    p = 2.0 * norm_sf(abs(z))
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    zc = norm_ppf(1 - (1 - ci_level) / 2)
    lift = diff / p0 if p0 > 0 else None
    return ZTest(arm.name, control.name, diff, lift, z, min(1.0, p), diff - zc * se, diff + zc * se)


def spent_alpha(t: float, alpha: float, kind: Spending = "obrien_fleming") -> float:
    """Cumulative two-sided alpha spent by information fraction t (Lan and DeMets, 1983).

    Symmetric two-sided design: each side spends alpha/2 with the one-sided O'Brien-Fleming
    type function 2 - 2 * Phi(z_{1 - a/2} / sqrt(t)), a = alpha/2. This is the convention
    used by standard group-sequential software, so boundaries match published tables.
    """
    if t <= 0:
        return 0.0
    t = min(t, 1.0)
    if kind == "obrien_fleming":
        side = alpha / 2.0
        return 2.0 * (2.0 * norm_sf(norm_ppf(1 - side / 2) / math.sqrt(t)))
    if kind == "pocock":
        return alpha * math.log(1 + (math.e - 1) * t)
    raise ValueError(f"unknown spending function {kind!r}")


def boundaries(info_fractions: Sequence[float], alpha: float = 0.05, kind: Spending = "obrien_fleming") -> tuple[float, ...]:
    """Two-sided critical |z| at each planned look so total type I error equals alpha."""
    fr = tuple(round(float(t), 10) for t in info_fractions)
    if not fr or any(b <= a for a, b in zip(fr, fr[1:])) or fr[0] <= 0 or fr[-1] > 1 + 1e-9:
        raise ValueError(f"information fractions must be increasing in (0, 1], got {info_fractions}")
    return _boundaries(fr, float(alpha), kind)


@lru_cache(maxsize=256)
def _boundaries(fr: tuple[float, ...], alpha: float, kind: Spending, n: int = 161) -> tuple[float, ...]:
    out: list[float] = []
    prev_spent = 0.0
    grid: list[float] = []  # S-scale (S_k = Z_k * sqrt(t_k)) points of the continuation region
    dens: list[float] = []  # sub-density of S_k on that region (has not stopped yet)
    w: list[float] = []     # Simpson weights
    prev_t = 0.0
    for k, t in enumerate(fr):
        target = spent_alpha(t, alpha, kind) - prev_spent
        sd = math.sqrt(t - prev_t)
        if k == 0:
            c = norm_ppf(1 - target / 2) if target > 0 else 8.0
        else:
            def cross(c: float, t: float = t, sd: float = sd, grid=grid, dens=dens, w=w) -> float:
                b = c * math.sqrt(t)
                return sum(
                    wi * fi * (norm_cdf((-b - s) / sd) + norm_sf((b - s) / sd))
                    for s, fi, wi in zip(grid, dens, w)
                )
            if target <= 1e-14:
                c = 8.0
            else:
                lo, hi = 0.0, 10.0
                for _ in range(60):
                    mid = 0.5 * (lo + hi)
                    if cross(mid) > target:
                        lo = mid
                    else:
                        hi = mid
                c = 0.5 * (lo + hi)
        out.append(c)
        # Carry the density forward over the continuation region (-c sqrt t, c sqrt t).
        b = c * math.sqrt(t)
        h = 2 * b / (n - 1)
        new_grid = [-b + i * h for i in range(n)]
        new_w = [h / 3 * (1 if i in (0, n - 1) else (4 if i % 2 else 2)) for i in range(n)]
        if k == 0:
            new_dens = [norm_pdf(u / sd) / sd for u in new_grid]
        else:
            new_dens = [
                sum(wi * fi * norm_pdf((u - s) / sd) / sd for s, fi, wi in zip(grid, dens, w))
                for u in new_grid
            ]
        grid, dens, w = new_grid, new_dens, new_w
        prev_spent += target
        prev_t = t
    return tuple(out)


def required_sample_per_arm(
    baseline: float,
    relative_mde: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    comparisons: int = 1,
) -> int:
    """Fixed-horizon visitors per arm for a two-sided two-proportion test (Bonferroni split)."""
    if not 0 < baseline < 1:
        raise ValueError("baseline must be in (0, 1)")
    p1 = baseline
    p2 = baseline * (1 + relative_mde)
    if not 0 < p2 < 1:
        raise ValueError("baseline * (1 + mde) must be in (0, 1)")
    a = alpha / max(1, comparisons)
    za = norm_ppf(1 - a / 2)
    zb = norm_ppf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)
