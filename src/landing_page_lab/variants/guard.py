"""Copy guard: generated copy may not invent numbers or reach for hype.

Every number in a headline, subhead or CTA must appear somewhere in the brief. This is
the rule that stops a generator (offline or LLM) from writing "3x more bookings" when
nobody measured that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from ..brief import Brief
from .provider import SECTIONS, Variant

NUM = re.compile(r"\d+(?:[.,]\d+)?")
HYPE = ("revolutionary", "best-in-class", "world-class", "game-changing", "game changer", "guaranteed",
        "#1", "number one", "unbeatable", "skyrocket", "10x", "cutting-edge", "seamless", "unleash")
LIMITS = {"headline": 80, "subhead": 200, "cta": 32}


@dataclass(frozen=True)
class GuardIssue:
    variant: str
    field: str
    message: str


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM.findall(text)}


def check_variant(brief: Brief, v: Variant) -> list[GuardIssue]:
    issues: list[GuardIssue] = []
    allowed = _numbers(brief.fact_text())
    for fld, limit in LIMITS.items():
        text = getattr(v, fld)
        if not text.strip():
            issues.append(GuardIssue(v.key, fld, "is empty"))
            continue
        if len(text) > limit:
            issues.append(GuardIssue(v.key, fld, f"{len(text)} chars, max {limit}"))
        invented = sorted(_numbers(text) - allowed)
        if invented:
            issues.append(GuardIssue(v.key, fld, f"numbers not in the brief: {', '.join(invented)}"))
        low = text.lower()
        for word in HYPE:
            if word in low:
                issues.append(GuardIssue(v.key, fld, f"hype word {word!r}"))
        if "\u2014" in text:
            issues.append(GuardIssue(v.key, fld, "em dash (house style: none)"))
    unknown = [s for s in v.section_order if s not in SECTIONS]
    if unknown:
        issues.append(GuardIssue(v.key, "section_order", f"unknown sections: {unknown}"))
    if len(set(v.section_order)) != len(v.section_order):
        issues.append(GuardIssue(v.key, "section_order", "repeats a section"))
    if not v.section_order or v.section_order[-1] != "cta":
        issues.append(GuardIssue(v.key, "section_order", "must end with the cta section"))
    if v.hero_proof is not None and v.hero_proof not in {p.id for p in brief.proof}:
        issues.append(GuardIssue(v.key, "hero_proof", f"unknown proof id {v.hero_proof!r}"))
    return issues


def check_variants(brief: Brief, variants: Sequence[Variant]) -> list[GuardIssue]:
    issues: list[GuardIssue] = []
    keys = [v.key for v in variants]
    if len(set(keys)) != len(keys):
        issues.append(GuardIssue("*", "key", f"duplicate keys {keys}"))
    if sum(v.is_control for v in variants) != 1:
        issues.append(GuardIssue("*", "is_control", "exactly one variant must be the control"))
    heads = [v.headline.lower() for v in variants]
    if len(set(heads)) != len(heads):
        issues.append(GuardIssue("*", "headline", "two variants share a headline, so the test cannot tell them apart"))
    for v in variants:
        issues.extend(check_variant(brief, v))
    return issues
