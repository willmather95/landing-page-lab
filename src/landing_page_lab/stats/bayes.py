"""Bayesian beta-binomial readout.

Each arm's conversion rate gets a Beta(prior_a + conversions, prior_b + misses) posterior.
Probability to be best and expected loss are computed by deterministic numerical
integration on a shared grid, so the same counts always give the same answer:

    P(arm k is best) = integral f_k(x) * prod_{j != k} F_j(x) dx
    E[max]           = integral x dG(x),  G(x) = prod_j F_j(x)
    expected loss_k  = E[max] - E[theta_k]

Expected loss is "how much conversion rate I give up, on average, if I ship arm k and
it is not actually the best". A Monte Carlo cross-check lives in `monte_carlo`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from ._math import log_beta
from .types import ArmCounts


@dataclass(frozen=True)
class Posterior:
    name: str
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def sd(self) -> float:
        a, b = self.alpha, self.beta
        return math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))

    def logpdf(self, x: float) -> float:
        if x <= 0.0 or x >= 1.0:
            return -math.inf
        return (self.alpha - 1) * math.log(x) + (self.beta - 1) * math.log1p(-x) - log_beta(self.alpha, self.beta)


@dataclass(frozen=True)
class BayesArm:
    name: str
    mean: float
    ci_low: float
    ci_high: float
    prob_best: float
    expected_loss: float
    prob_beats_control: float | None


@dataclass(frozen=True)
class BayesResult:
    arms: tuple[BayesArm, ...]
    method: str

    def by_name(self, name: str) -> BayesArm:
        for arm in self.arms:
            if arm.name == name:
                return arm
        raise KeyError(name)

    @property
    def leader(self) -> BayesArm:
        return max(self.arms, key=lambda a: (a.prob_best, -a.expected_loss))


def posteriors(arms: Sequence[ArmCounts], prior: tuple[float, float] = (1.0, 1.0)) -> list[Posterior]:
    a0, b0 = prior
    if a0 <= 0 or b0 <= 0:
        raise ValueError("prior parameters must be > 0")
    return [Posterior(a.name, a0 + a.conversions, b0 + a.visitors - a.conversions) for a in arms]


@dataclass(frozen=True)
class _Grid:
    xs: list[float]
    dx: float
    pdfs: list[list[float]]
    cdfs: list[list[float]]


def _build_grid(posts: Sequence[Posterior], points: int) -> _Grid:
    lo = max(1e-12, min(p.mean - 9 * p.sd for p in posts))
    hi = min(1 - 1e-12, max(p.mean + 9 * p.sd for p in posts))
    if hi <= lo:  # degenerate, every posterior is a spike at the same place
        lo, hi = max(1e-12, lo - 1e-6), min(1 - 1e-12, hi + 1e-6)
    dx = (hi - lo) / (points - 1)
    xs = [lo + i * dx for i in range(points)]
    pdfs: list[list[float]] = []
    cdfs: list[list[float]] = []
    for p in posts:
        raw = [math.exp(p.logpdf(x)) if 0 < x < 1 else 0.0 for x in xs]
        # Trapezoid CDF, then renormalize so discretization error cannot leak into P(best).
        cdf = [0.0]
        for i in range(1, points):
            cdf.append(cdf[-1] + 0.5 * (raw[i] + raw[i - 1]) * dx)
        total = cdf[-1] or 1.0
        pdfs.append([v / total for v in raw])
        cdfs.append([v / total for v in cdf])
    return _Grid(xs, dx, pdfs, cdfs)


def _quantile(xs: list[float], cdf: list[float], q: float) -> float:
    for i in range(1, len(xs)):
        if cdf[i] >= q:
            span = cdf[i] - cdf[i - 1]
            frac = (q - cdf[i - 1]) / span if span > 0 else 0.0
            return xs[i - 1] + frac * (xs[i] - xs[i - 1])
    return xs[-1]


def analyze(
    arms: Sequence[ArmCounts],
    *,
    control: str | None = None,
    prior: tuple[float, float] = (1.0, 1.0),
    points: int = 3001,
    credible: float = 0.95,
) -> BayesResult:
    """Posterior summary, probability to be best and expected loss for every arm."""
    if len(arms) < 2:
        raise ValueError("need at least two arms")
    posts = posteriors(arms, prior)
    g = _build_grid(posts, points)
    k = len(posts)
    n = len(g.xs)

    # Product of all CDFs, and leave-one-out products, at every grid point.
    prob_best = [0.0] * k
    joint = [1.0] * n
    for i in range(n):
        prod = 1.0
        for j in range(k):
            prod *= g.cdfs[j][i]
        joint[i] = prod
        for j in range(k):
            c = g.cdfs[j][i]
            others = prod / c if c > 1e-300 else _prod_except(g.cdfs, i, j)
            prob_best[j] += g.pdfs[j][i] * others * g.dx
    s = sum(prob_best) or 1.0
    prob_best = [p / s for p in prob_best]

    e_max = 0.0
    for i in range(1, n):
        e_max += 0.5 * (g.xs[i] + g.xs[i - 1]) * (joint[i] - joint[i - 1])
    e_max += g.xs[0] * joint[0]

    means = [sum(x * f for x, f in zip(g.xs, pdf)) * g.dx for pdf in g.pdfs]
    ctrl_idx = None
    if control is not None:
        names = [a.name for a in arms]
        if control not in names:
            raise KeyError(f"control arm {control!r} not in {names}")
        ctrl_idx = names.index(control)

    tail = (1.0 - credible) / 2.0
    out = []
    for j, post in enumerate(posts):
        beats = None
        if ctrl_idx is not None and j != ctrl_idx:
            beats = min(1.0, max(0.0, sum(g.pdfs[j][i] * g.cdfs[ctrl_idx][i] for i in range(n)) * g.dx))
        out.append(
            BayesArm(
                name=post.name,
                mean=post.mean,
                ci_low=_quantile(g.xs, g.cdfs[j], tail),
                ci_high=_quantile(g.xs, g.cdfs[j], 1.0 - tail),
                prob_best=prob_best[j],
                expected_loss=max(0.0, e_max - means[j]),
                prob_beats_control=beats,
            )
        )
    return BayesResult(tuple(out), method=f"grid({points})")


def _prod_except(cdfs: list[list[float]], i: int, skip: int) -> float:
    prod = 1.0
    for j, cdf in enumerate(cdfs):
        if j != skip:
            prod *= cdf[i]
    return prod


def monte_carlo(
    arms: Sequence[ArmCounts],
    *,
    draws: int = 20_000,
    seed: int = 0,
    prior: tuple[float, float] = (1.0, 1.0),
) -> tuple[list[float], list[float]]:
    """(prob_best, expected_loss) by sampling. Used to cross-check the grid integrator."""
    posts = posteriors(arms, prior)
    rng = random.Random(seed)
    wins = [0] * len(posts)
    loss = [0.0] * len(posts)
    for _ in range(draws):
        sample = [rng.betavariate(p.alpha, p.beta) for p in posts]
        best = max(sample)
        wins[sample.index(best)] += 1
        for j, v in enumerate(sample):
            loss[j] += best - v
    return [w / draws for w in wins], [x / draws for x in loss]


def relative_uplift_interval(
    arm: ArmCounts,
    control: ArmCounts,
    *,
    draws: int = 20_000,
    seed: int = 0,
    credible: float = 0.95,
    prior: tuple[float, float] = (1.0, 1.0),
) -> tuple[float, float, float]:
    """Median and equal-tailed credible interval of (theta_arm / theta_control - 1)."""
    pa, pc = posteriors([arm, control], prior)
    rng = random.Random(seed)
    ups = sorted(rng.betavariate(pa.alpha, pa.beta) / rng.betavariate(pc.alpha, pc.beta) - 1.0 for _ in range(draws))
    tail = (1.0 - credible) / 2.0

    def pick(q: float) -> float:
        return ups[min(len(ups) - 1, max(0, int(q * len(ups))))]

    return pick(0.5), pick(tail), pick(1.0 - tail)
