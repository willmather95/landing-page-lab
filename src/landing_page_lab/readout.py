"""Experiment readout: one decision from two independent tests plus a data-quality gate.

A winner is called only when ALL of these hold at a planned look:

1. No sample ratio mismatch (chi-square, p >= 0.001).
2. Minimum sample: every arm has enough visitors and conversions.
3. Bayesian gate: the leader's probability to be best >= 95% and its expected loss
   <= 1% of the control rate (both configurable).
4. Frequentist gate: the leader beats control (or control beats every challenger) with
   |z| past the group-sequential boundary for this look, Bonferroni-split across the
   challenger-vs-control comparisons.

Otherwise the answer is "keep running". At the final look with no winner the answer is
"no winner: keep control". Between looks the numbers are shown but no call is made,
because deciding on every peek is how A/B tests lie.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from .stats import ArmCounts, analyze, boundaries, relative_uplift_interval, srm_check, two_proportion_ztest
from .stats.bayes import BayesResult
from .stats.frequentist import Spending, ZTest
from .stats.srm import SrmResult


class Status(str, Enum):
    WINNER = "winner"
    KEEP_RUNNING = "keep_running"
    NO_WINNER = "no_winner_keep_control"
    INVALID_SRM = "invalid_sample_ratio_mismatch"


@dataclass(frozen=True)
class Policy:
    alpha: float = 0.05
    spending: Spending = "obrien_fleming"
    look_days: tuple[int, ...] = (7, 14, 21)
    min_visitors_per_arm: int = 1000
    min_conversions_per_arm: int = 30
    prob_best_threshold: float = 0.95
    max_expected_loss_rel: float = 0.01
    srm_threshold: float = 0.001

    def __post_init__(self) -> None:
        if not self.look_days or list(self.look_days) != sorted(set(self.look_days)) or self.look_days[0] < 1:
            raise ValueError("look_days must be strictly increasing positive days")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        if not 0.5 < self.prob_best_threshold < 1:
            raise ValueError("prob_best_threshold must be in (0.5, 1)")

    @property
    def info_fractions(self) -> tuple[float, ...]:
        last = self.look_days[-1]
        return tuple(d / last for d in self.look_days)


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ArmRow:
    name: str
    visitors: int
    conversions: int
    rate: float
    posterior_mean: float
    ci_low: float
    ci_high: float
    prob_best: float
    expected_loss: float
    prob_beats_control: float | None
    z: float | None
    p_value: float | None
    lift: float | None
    lift_ci: tuple[float, float] | None


@dataclass(frozen=True)
class Readout:
    day: int | None
    look: int | None
    status: Status
    winner: str | None
    leader: str
    control: str
    arms: tuple[ArmRow, ...]
    srm: SrmResult
    boundary_z: float | None
    gates: tuple[Gate, ...]
    next_look_day: int | None
    policy: Policy
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def decided(self) -> bool:
        return self.status in (Status.WINNER, Status.NO_WINNER, Status.INVALID_SRM)

    def arm(self, name: str) -> ArmRow:
        return next(a for a in self.arms if a.name == name)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def headline(self) -> str:
        if self.status is Status.WINNER:
            row = self.arm(self.winner or self.leader)
            if self.winner == self.control:
                return f"Winner: {self.winner} (control beats every challenger, P(best) {row.prob_best:.1%})"
            return f"Winner: {self.winner} ({_pct_signed(row.lift)} vs {self.control}, P(best) {row.prob_best:.1%})"
        if self.status is Status.INVALID_SRM:
            return f"Stop: sample ratio mismatch (p = {self.srm.p_value:.2g}). Fix assignment before reading results."
        if self.status is Status.NO_WINNER:
            return f"No winner at the final look. Keep {self.control}."
        nxt = f" Next decision on day {self.next_look_day}." if self.next_look_day else ""
        return f"Keep running. Leader so far: {self.leader}.{nxt}"

    def to_markdown(self, title: str = "Experiment readout") -> str:
        lines = [f"# {title}", ""]
        when = f"Day {self.day}" if self.day is not None else "Ad hoc"
        look = f", look {self.look + 1} of {len(self.policy.look_days)}" if self.look is not None else ", between looks"
        lines += [f"**{self.headline()}**", "", f"{when}{look}. Status: `{self.status.value}`.", ""]
        lines += [
            "| Variant | Visitors | Conversions | Rate | 95% credible | P(best) | Exp. loss | Lift vs control | z | p |",
            "|---|---:|---:|---:|---|---:|---:|---|---:|---:|",
        ]
        for a in self.arms:
            lift = "control" if a.name == self.control else _lift_cell(a)
            z = "" if a.z is None else f"{a.z:.2f}"
            p = "" if a.p_value is None else f"{a.p_value:.4f}"
            lines.append(
                f"| {a.name} | {a.visitors:,} | {a.conversions:,} | {a.rate:.2%} | {a.ci_low:.2%} to {a.ci_high:.2%} "
                f"| {a.prob_best:.1%} | {a.expected_loss * 100:.3f} pts | {lift} | {z} | {p} |"
            )
        lines += ["", "## Gates", ""]
        for g in self.gates:
            lines.append(f"- {'PASS' if g.passed else 'FAIL'} **{g.name}**: {g.detail}")
        lines += ["", "## Data quality", ""]
        exp = ", ".join(f"{e:,.0f}" for e in self.srm.expected)
        obs = ", ".join(f"{o:,}" for o in self.srm.observed)
        lines.append(
            f"- Sample ratio check: observed {obs} vs expected {exp}; chi-square {self.srm.chi2:.2f}, "
            f"p = {self.srm.p_value:.3g} ({'MISMATCH' if self.srm.mismatch else 'ok'}, threshold {self.policy.srm_threshold})."
        )
        lines += ["", "## How this was decided", ""]
        b = boundaries(self.policy.info_fractions, self.policy.alpha / max(1, len(self.arms) - 1), self.policy.spending)
        bl = ", ".join(f"day {d}: |z| >= {z:.2f}" for d, z in zip(self.policy.look_days, b))
        lines += [
            f"- Planned looks only ({bl}). Lan-DeMets {self.policy.spending.replace('_', '-')} alpha spending, "
            f"total alpha {self.policy.alpha}, split across {max(1, len(self.arms) - 1)} challenger comparisons.",
            f"- Bayesian gate: Beta(1, 1) prior, P(best) >= {self.policy.prob_best_threshold:.0%} and expected loss "
            f"<= {self.policy.max_expected_loss_rel:.0%} of the control rate.",
            f"- Minimum per arm: {self.policy.min_visitors_per_arm:,} visitors and {self.policy.min_conversions_per_arm} conversions.",
            "- A daily fixed-horizon p-value is shown for context only. Acting on it at every peek inflates false winners.",
        ]
        for n in self.notes:
            lines.append(f"- {n}")
        return "\n".join(lines) + "\n"


def _pct_signed(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def _lift_cell(a: ArmRow) -> str:
    if a.lift is None:
        return "n/a"
    if a.lift_ci is None:
        return _pct_signed(a.lift)
    return f"{_pct_signed(a.lift)} ({a.lift_ci[0]:+.1%} to {a.lift_ci[1]:+.1%})"


def _coerce(arms: Sequence[ArmCounts] | Mapping[str, tuple[int, int]]) -> list[ArmCounts]:
    if isinstance(arms, Mapping):
        return [ArmCounts(k, int(v[0]), int(v[1])) for k, v in arms.items()]
    return list(arms)


def readout(
    arms: Sequence[ArmCounts] | Mapping[str, tuple[int, int]],
    *,
    control: str | None = None,
    weights: Sequence[float] | None = None,
    day: int | None = None,
    policy: Policy | None = None,
    detail: bool = True,
    seed: int = 0,
) -> Readout:
    """Read an experiment and decide: winner, keep running, no winner, or invalid.

    arms:    ArmCounts list, or {"control": (visitors, conversions), ...}
    control: control arm name (default: first arm)
    weights: planned traffic split (default: equal)
    day:     days since launch. Decisions happen only on policy.look_days. None = report only.
    detail:  compute Monte Carlo lift intervals (skip in large simulations for speed)
    """
    policy = policy or Policy()
    rows = _coerce(arms)
    if len(rows) < 2:
        raise ValueError("need at least two arms")
    names = [r.name for r in rows]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate arm names: {names}")
    control = control or names[0]
    if control not in names:
        raise KeyError(f"control {control!r} not in {names}")
    weights = list(weights) if weights is not None else [1.0] * len(rows)

    srm = srm_check(rows, weights, threshold=policy.srm_threshold)
    bayes: BayesResult = analyze(rows, control=control)
    ctrl = rows[names.index(control)]
    m = len(rows) - 1
    tests: dict[str, ZTest] = {r.name: two_proportion_ztest(r, ctrl) for r in rows if r.name != control}

    look: int | None = None
    next_look: int | None = None
    if day is not None:
        if day in policy.look_days:
            look = policy.look_days.index(day)
        elif day > policy.look_days[-1]:
            look = len(policy.look_days) - 1
        next_look = next((d for d in policy.look_days if d > day), None)
    bnds = boundaries(policy.info_fractions, policy.alpha / m, policy.spending)
    boundary = bnds[look] if look is not None else None

    leader = bayes.leader
    gates: list[Gate] = []
    gates.append(Gate("Sample ratio", not srm.mismatch, f"p = {srm.p_value:.3g} (stop if < {policy.srm_threshold})"))
    small = [r.name for r in rows if r.visitors < policy.min_visitors_per_arm or r.conversions < policy.min_conversions_per_arm]
    gates.append(Gate("Minimum sample", not small, "all arms above minimum" if not small else f"below minimum: {', '.join(small)}"))
    loss_cap = policy.max_expected_loss_rel * max(ctrl.rate, 1e-9)
    bayes_ok = leader.prob_best >= policy.prob_best_threshold and leader.expected_loss <= loss_cap
    gates.append(
        Gate(
            "Bayesian",
            bayes_ok,
            f"{leader.name}: P(best) {leader.prob_best:.1%} (need {policy.prob_best_threshold:.0%}), "
            f"expected loss {leader.expected_loss * 100:.3f} pts (cap {loss_cap * 100:.3f})",
        )
    )
    if boundary is None:
        gates.append(Gate("Sequential z-test", False, "not a planned look, no decision allowed"))
        freq_ok = False
    elif leader.name == control:
        worst = max(t.z for t in tests.values())
        freq_ok = all(t.z <= -boundary for t in tests.values())
        gates.append(Gate("Sequential z-test", freq_ok, f"control vs every challenger: max challenger z {worst:.2f}, need <= {-boundary:.2f}"))
    else:
        t = tests[leader.name]
        freq_ok = t.z >= boundary
        gates.append(Gate("Sequential z-test", freq_ok, f"{leader.name} vs {control}: z {t.z:.2f}, need >= {boundary:.2f}"))

    if srm.mismatch:
        status = Status.INVALID_SRM
    elif look is not None and all(g.passed for g in gates):
        status = Status.WINNER
    elif look is not None and look == len(policy.look_days) - 1:
        status = Status.NO_WINNER
    else:
        status = Status.KEEP_RUNNING

    arm_rows = []
    for r in rows:
        b = bayes.by_name(r.name)
        t = tests.get(r.name)
        lift_ci = None
        if detail and t is not None and ctrl.conversions > 0:
            _, lo, hi = relative_uplift_interval(r, ctrl, seed=seed, draws=10_000)
            lift_ci = (lo, hi)
        arm_rows.append(
            ArmRow(
                name=r.name, visitors=r.visitors, conversions=r.conversions, rate=r.rate,
                posterior_mean=b.mean, ci_low=b.ci_low, ci_high=b.ci_high, prob_best=b.prob_best,
                expected_loss=b.expected_loss, prob_beats_control=b.prob_beats_control,
                z=None if t is None else t.z, p_value=None if t is None else t.p_value,
                lift=None if t is None else t.relative_lift, lift_ci=lift_ci,
            )
        )

    notes: list[str] = []
    if day is not None and look is None:
        notes.append(f"Day {day} is between planned looks. Numbers are informational only.")
    if day is not None and day > policy.look_days[-1]:
        notes.append("Past the final planned look: treated as the final look.")
    return Readout(
        day=day, look=look, status=status, winner=leader.name if status is Status.WINNER else None,
        leader=leader.name, control=control, arms=tuple(arm_rows), srm=srm, boundary_z=boundary,
        gates=tuple(gates), next_look_day=next_look if status is Status.KEEP_RUNNING else None,
        policy=policy, notes=tuple(notes),
    )
