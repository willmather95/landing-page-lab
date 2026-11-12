"""Sample ratio mismatch: did traffic split the way the flag said it would?

A chi-square goodness-of-fit test on visitor counts. A tiny p-value (default < 0.001)
means the assignment or the tracking is broken, so no result should be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ._math import chi2_sf
from .types import ArmCounts


@dataclass(frozen=True)
class SrmResult:
    chi2: float
    p_value: float
    expected: tuple[float, ...]
    observed: tuple[int, ...]
    mismatch: bool


def srm_check(arms: Sequence[ArmCounts], weights: Sequence[float], *, threshold: float = 0.001) -> SrmResult:
    if len(arms) != len(weights):
        raise ValueError("one weight per arm")
    total_w = float(sum(weights))
    if total_w <= 0 or any(w <= 0 for w in weights):
        raise ValueError("weights must be positive")
    n = sum(a.visitors for a in arms)
    observed = tuple(a.visitors for a in arms)
    expected = tuple(n * w / total_w for w in weights)
    if n == 0:
        return SrmResult(0.0, 1.0, expected, observed, False)
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected))
    p = chi2_sf(chi2, len(arms) - 1)
    return SrmResult(chi2, p, expected, observed, p < threshold)
