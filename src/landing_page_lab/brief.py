"""The brief: everything a variant is allowed to say, in one YAML file.

Generated copy may only use facts that appear here. In particular every number in a
headline, subhead or proof block must come from this file (see variants/guard.py).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

_KEY = re.compile(r"^[a-z][a-z0-9-]{1,48}$")


DEFAULT_HEADINGS = {
    "problem": "What it costs you today",
    "how": "How it works",
    "proof": "Results",
    "features": "What you get",
    "faq": "Questions",
}


class BriefError(ValueError):
    pass


@dataclass(frozen=True)
class Proof:
    id: str
    stat: str          # "31%" or "4.8 / 5" (the exact figure, as it may appear on the page)
    label: str         # "fewer no-shows in the first 60 days"
    source: str        # where the number comes from; shown in the footnote


@dataclass(frozen=True)
class Testimonial:
    quote: str
    name: str
    role: str


@dataclass(frozen=True)
class Step:
    title: str
    body: str


@dataclass(frozen=True)
class Feature:
    title: str
    body: str


@dataclass(frozen=True)
class Faq:
    q: str
    a: str


@dataclass(frozen=True)
class ExperimentPlan:
    key: str
    primary_event: str = "lpl_signup"
    baseline_rate: float = 0.04
    relative_mde: float = 0.20
    daily_visitors: int = 2000
    variants: int = 3
    alpha: float = 0.05
    power: float = 0.8


@dataclass(frozen=True)
class Brief:
    product: str
    one_liner: str
    category: str
    audience: str
    outcome: str
    pains: tuple[str, ...]
    primary_cta: str
    alt_ctas: tuple[str, ...]
    risk_reversal: str
    proof: tuple[Proof, ...]
    steps: tuple[Step, ...]
    features: tuple[Feature, ...]
    faq: tuple[Faq, ...]
    testimonials: tuple[Testimonial, ...]
    experiment: ExperimentPlan
    brand_color: str = "#0a72e8"
    disclaimer: str = ""
    headings: dict[str, str] = field(default_factory=dict)

    def heading(self, section: str) -> str:
        return self.headings.get(section) or DEFAULT_HEADINGS[section]

    def fingerprint(self) -> str:
        """Stable hash of the brief: same brief, same variants."""
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def fact_text(self) -> str:
        """All text the copy guard treats as an allowed source of numbers and claims."""
        parts = [self.product, self.one_liner, self.category, self.audience, self.outcome, self.primary_cta,
                 self.risk_reversal, *self.pains, *self.alt_ctas]
        for p in self.proof:
            parts += [p.stat, p.label]
        for s in self.steps:
            parts += [s.title, s.body]
        for f in self.features:
            parts += [f.title, f.body]
        for q in self.faq:
            parts += [q.q, q.a]
        for t in self.testimonials:
            parts += [t.quote]
        parts += list(self.headings.values())
        return "\n".join(parts)


def _req(d: dict, key: str, where: str) -> Any:
    if key not in d or d[key] in (None, "", []):
        raise BriefError(f"{where}.{key} is required")
    return d[key]


def _str(d: dict, key: str, where: str, max_len: int = 400) -> str:
    v = _req(d, key, where)
    if not isinstance(v, str):
        raise BriefError(f"{where}.{key} must be a string")
    v = " ".join(v.split())
    if len(v) > max_len:
        raise BriefError(f"{where}.{key} is {len(v)} chars, max {max_len}")
    return v


def parse_brief(data: dict) -> Brief:
    if not isinstance(data, dict):
        raise BriefError("brief must be a mapping")
    p = _req(data, "product", "brief")
    a = _req(data, "audience", "brief")
    o = _req(data, "offer", "brief")
    e = data.get("experiment") or {}

    proofs = []
    for i, item in enumerate(_req(data, "proof", "brief")):
        where = f"proof[{i}]"
        pid = str(item.get("id") or f"p{i + 1}")
        proofs.append(Proof(pid, _str(item, "stat", where, 24), _str(item, "label", where, 90), _str(item, "source", where, 200)))
    if len({p.id for p in proofs}) != len(proofs):
        raise BriefError("proof ids must be unique")

    key = str(e.get("key") or "")
    if not _KEY.match(key):
        raise BriefError("experiment.key must be lowercase letters, digits and dashes (2-49 chars)")
    plan = ExperimentPlan(
        key=key,
        primary_event=str(e.get("primary_event", "lpl_signup")),
        baseline_rate=float(e.get("baseline_rate", 0.04)),
        relative_mde=float(e.get("relative_mde", 0.20)),
        daily_visitors=int(e.get("daily_visitors", 2000)),
        variants=int(e.get("variants", 3)),
        alpha=float(e.get("alpha", 0.05)),
        power=float(e.get("power", 0.8)),
    )
    if not 2 <= plan.variants <= 5:
        raise BriefError("experiment.variants must be 2 to 5")
    if not 0 < plan.baseline_rate < 1 or plan.relative_mde <= 0:
        raise BriefError("experiment.baseline_rate must be in (0, 1) and relative_mde > 0")

    color = str(data.get("brand_color", "#0a72e8"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise BriefError("brand_color must be #rrggbb")

    return Brief(
        product=_str(p, "name", "product", 40),
        one_liner=_str(p, "one_liner", "product", 120),
        category=_str(p, "category", "product", 60),
        audience=_str(a, "who", "audience", 120),
        outcome=_str(a, "desired_outcome", "audience", 120),
        pains=tuple(" ".join(str(x).split()) for x in _req(a, "pains", "audience")),
        primary_cta=_str(o, "primary_cta", "offer", 32),
        alt_ctas=tuple(" ".join(str(x).split()) for x in o.get("alt_ctas", [])),
        risk_reversal=_str(o, "risk_reversal", "offer", 120),
        proof=tuple(proofs),
        steps=tuple(Step(_str(s, "title", "steps", 60), _str(s, "body", "steps", 200)) for s in data.get("steps", [])),
        features=tuple(Feature(_str(f, "title", "features", 60), _str(f, "body", "features", 200)) for f in data.get("features", [])),
        faq=tuple(Faq(_str(f, "q", "faq", 120), _str(f, "a", "faq", 400)) for f in data.get("faq", [])),
        testimonials=tuple(
            Testimonial(_str(t, "quote", "testimonials", 240), _str(t, "name", "testimonials", 60), _str(t, "role", "testimonials", 80))
            for t in data.get("testimonials", [])
        ),
        experiment=plan,
        brand_color=color,
        disclaimer=str(data.get("disclaimer", "")),
        headings=_headings(data.get("headings") or {}),
    )


def _headings(raw: dict) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise BriefError("headings must be a mapping")
    unknown = set(raw) - set(DEFAULT_HEADINGS)
    if unknown:
        raise BriefError(f"unknown heading keys: {sorted(unknown)}")
    return {k: _str(raw, k, "headings", 80) for k in raw}


def load_brief(path: str | Path) -> Brief:
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BriefError(f"{path}: invalid YAML: {exc}") from exc
    return parse_brief(data)
