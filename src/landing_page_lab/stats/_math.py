"""Small numeric helpers so the stats layer has zero third-party dependencies.

Everything here is textbook (Numerical Recipes style) and covered by tests against
known reference values.
"""

from __future__ import annotations

import math
from statistics import NormalDist

_STD = NormalDist()


def norm_cdf(z: float) -> float:
    return _STD.cdf(z)


def norm_sf(z: float) -> float:
    """Upper tail P(Z > z), computed without cancellation for large z."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    return _STD.inv_cdf(p)


def norm_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _gamma_series(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x) by series (good for x < a + 1)."""
    term = 1.0 / a
    total = term
    ap = a
    for _ in range(10_000):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) by Lentz continued fraction (x >= a + 1)."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gamma_q(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) = 1 - P(a, x)."""
    if x < 0 or a <= 0:
        raise ValueError("gamma_q needs x >= 0 and a > 0")
    if x == 0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gamma_series(a, x)
    return _gamma_cf(a, x)


def chi2_sf(x: float, df: int) -> float:
    """Survival function of the chi-square distribution."""
    if df < 1:
        raise ValueError("df must be >= 1")
    if x <= 0:
        return 1.0
    return gamma_q(df / 2.0, x / 2.0)


def log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
