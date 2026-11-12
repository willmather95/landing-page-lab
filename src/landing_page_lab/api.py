"""The two calls other systems (like channel-loop) make.

    handle = create_experiment("brief.yaml", out_dir="out/exp")       # variants, build, PostHog plan
    result = readout({"a": (9000, 360), "b": (9000, 380), "c": (9000, 430)}, day=14, handle=handle)

Both default to offline: the offline variant provider and a dry-run PostHog client.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .brief import Brief, load_brief
from .posthog.client import CreatedExperiment, PostHogClient
from .posthog.snippet import config_for, rollout
from .readout import Policy, Readout
from .readout import readout as _readout
from .site.build import BuildResult, build_site
from .stats import ArmCounts, required_sample_per_arm
from .variants import Variant, VariantProvider, generate_variants


@dataclass(frozen=True)
class TrafficPlan:
    visitors_per_arm: int
    total_visitors: int
    days_needed: int
    look_days: tuple[int, ...]
    note: str

    def policy(self, **overrides) -> Policy:
        return Policy(look_days=self.look_days, **overrides)


def plan_traffic(brief: Brief, arms: int | None = None) -> TrafficPlan:
    """Size the test, then round up to whole weeks so every look sees each weekday equally."""
    e = brief.experiment
    k = arms or e.variants
    n = required_sample_per_arm(e.baseline_rate, e.relative_mde, alpha=e.alpha, power=e.power, comparisons=k - 1)
    total = n * k
    days = math.ceil(total / e.daily_visitors)
    weeks = max(2, math.ceil(days / 7))
    looks = tuple(7 * w for w in range(1, weeks + 1))
    note = (f"{n:,} visitors per arm detects a {e.relative_mde:.0%} relative lift on a {e.baseline_rate:.1%} baseline "
            f"with {e.power:.0%} power (alpha {e.alpha} split over {k - 1} comparisons). "
            f"At {e.daily_visitors:,} visitors a day that is {days} days, rounded up to {weeks} full weeks. "
            "Group-sequential looks add a few percent to the worst-case sample.")
    return TrafficPlan(n, total, days, looks, note)


@dataclass(frozen=True)
class ExperimentHandle:
    brief: Brief
    variants: tuple[Variant, ...]
    plan: TrafficPlan
    build: BuildResult | None
    posthog: CreatedExperiment
    dry_run: bool

    @property
    def key(self) -> str:
        return self.brief.experiment.key

    @property
    def control(self) -> str:
        return next(v.key for v in self.variants if v.is_control)

    @property
    def weights(self) -> tuple[float, ...]:
        """The flag's exact rollout split (e.g. 34/33/33). The SRM check must use this, not 'equal'."""
        return tuple(float(p) for p in rollout(len(self.variants)))

    def policy(self) -> Policy:
        return self.plan.policy()

    def summary(self) -> dict:
        return {
            "experiment": self.key,
            "dry_run": self.dry_run,
            "control": self.control,
            "variants": [v.to_dict() for v in self.variants],
            "plan": self.plan.__dict__,
            "dist": str(self.build.dist) if self.build else None,
            "posthog": {"experiment_id": self.posthog.experiment_id, "flag_key": self.posthog.flag_key},
        }


def create_experiment(
    brief: Brief | str | Path,
    *,
    out_dir: str | Path | None = None,
    provider: VariantProvider | None = None,
    posthog: PostHogClient | None = None,
    posthog_project_key: str = "",
    build: bool = True,
) -> ExperimentHandle:
    """Brief -> guarded variants -> static build -> PostHog draft experiment (dry-run by default)."""
    b = brief if isinstance(brief, Brief) else load_brief(brief)
    variants = tuple(generate_variants(b, provider))
    plan = plan_traffic(b, len(variants))
    client = posthog or PostHogClient.dry_run()
    built = None
    out = Path(out_dir) if out_dir else None
    if build:
        if out is None:
            raise ValueError("out_dir is required when build=True")
        cfg = config_for(b.experiment.key, variants, b.experiment.primary_event, api_key=posthog_project_key)
        built = build_site(b, variants, out / "dist", snippet=cfg)
    created = client.create_experiment(b.experiment.key, variants, primary_event=b.experiment.primary_event,
                                       relative_mde=b.experiment.relative_mde)
    handle = ExperimentHandle(b, variants, plan, built, created, client.is_dry_run)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "experiment.json").write_text(json.dumps(handle.summary(), indent=2, default=str) + "\n")
        (out / "posthog-requests.json").write_text(json.dumps(list(created.requests), indent=2) + "\n")
    return handle


def readout(
    counts: Sequence[ArmCounts] | Mapping[str, tuple[int, int]],
    *,
    day: int | None,
    handle: ExperimentHandle | None = None,
    policy: Policy | None = None,
    control: str | None = None,
    weights: Sequence[float] | None = None,
    detail: bool = True,
) -> Readout:
    """Decide on an experiment. With a handle, control, split and look days come from the plan."""
    if handle is not None:
        policy = policy or handle.policy()
        control = control or handle.control
        weights = weights or handle.weights
    return _readout(counts, control=control, weights=weights, day=day, policy=policy, detail=detail)
