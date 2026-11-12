"""Deterministic offline variant generator.

No network, no model, no randomness you cannot replay: the brief's fingerprint seeds
every choice, so the same brief always yields the same variants. Each variant tests one
angle (a reason to care) and carries a matching section order:

    a  outcome  (control)  lead with the result the buyer wants
    b  pain                lead with the problem they feel today
    c  proof               lead with the strongest sourced number
    d  steps               lead with how little effort it takes
    e  risk                lead with the risk reversal
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from ..brief import Brief
from .guard import LIMITS, _numbers
from .provider import VARIANT_KEYS, Variant


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _strip_period(s: str) -> str:
    return s.rstrip(" .")


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


@dataclass(frozen=True)
class _Angle:
    name: str
    headlines: tuple[Callable[[Brief], str], ...]
    subheads: tuple[Callable[[Brief], str], ...]
    order: tuple[str, ...]
    hero_proof: Callable[[Brief], str | None]
    why: str


def _top_proof(b: Brief) -> str | None:
    return b.proof[0].id if b.proof else None


def _proof_line(b: Brief) -> str:
    p = b.proof[0]
    return f"{p.stat} {p.label}"


ANGLES: tuple[_Angle, ...] = (
    _Angle(
        "outcome",
        (
            lambda b: _strip_period(b.one_liner),
            lambda b: f"{_cap(b.outcome)}, with {b.product}",
        ),
        (
            lambda b: f"{b.product} is {b.category} for {b.audience}. {b.risk_reversal}",
            lambda b: f"Built for {b.audience}. {b.risk_reversal}",
        ),
        ("how", "proof", "features", "testimonial", "faq", "cta"),
        _top_proof,
        "Control. Leads with the outcome the buyer wants, then shows how it works.",
    ),
    _Angle(
        "pain",
        (
            lambda b: f"{_strip_period(b.pains[0])}. {b.product} fixes that.",
            lambda b: f"{_strip_period(b.pains[0])}?",
            lambda b: _strip_period(b.pains[0]),
        ),
        (
            lambda b: f"{_cap(_strip_period(b.one_liner))}, so you get {b.outcome}. {b.risk_reversal}",
            lambda b: f"{b.product} gives {b.audience} {b.outcome}. {b.risk_reversal}",
        ),
        ("problem", "how", "proof", "testimonial", "features", "faq", "cta"),
        lambda b: None,
        "Names the problem first. Tests whether recognition beats promise for this audience.",
    ),
    _Angle(
        "proof",
        (
            lambda b: _cap(_proof_line(b)),
            lambda b: f"{_cap(_proof_line(b))} with {b.product}",
        ),
        (
            lambda b: f"{_cap(_strip_period(b.one_liner))}. Built for {b.audience}.",
            lambda b: f"{b.product} is {b.category} for {b.audience}. {b.risk_reversal}",
        ),
        ("proof", "testimonial", "how", "features", "faq", "cta"),
        lambda b: b.proof[1].id if len(b.proof) > 1 else None,  # headline already uses proof[0]
        "Leads with the strongest sourced number. Tests whether evidence beats story.",
    ),
    _Angle(
        "steps",
        (
            lambda b: f"{_cap(b.outcome)} in {len(b.steps)} steps",
            lambda b: f"{_cap(_lower_first(b.steps[0].title))}. That is most of the setup.",
        ),
        (
            lambda b: f"{b.steps[0].body} {b.risk_reversal}",
        ),
        ("how", "features", "proof", "faq", "cta"),
        lambda b: None,
        "Leads with effort. Tests whether setup worry is the real blocker.",
    ),
    _Angle(
        "risk",
        (
            lambda b: f"Try {b.product} free. {_strip_period(b.risk_reversal.split('.')[0])}.",
        ),
        (
            lambda b: f"{_cap(_strip_period(b.one_liner))} for {b.audience}.",
        ),
        ("faq", "how", "proof", "testimonial", "cta"),
        _top_proof,
        "Leads with the risk reversal. Tests whether fear of commitment is the blocker.",
    ),
)


class OfflineProvider:
    """Template-driven, seeded by the brief fingerprint. Zero network."""

    name = "offline"

    def generate(self, brief: Brief, count: int) -> list[Variant]:
        if not 2 <= count <= len(ANGLES):
            raise ValueError(f"offline provider makes 2 to {len(ANGLES)} variants")
        seed = int(brief.fingerprint()[:12], 16)
        out: list[Variant] = []
        for i, angle in enumerate(ANGLES[:count]):
            rng = random.Random(seed + i)
            headline = self._pick(rng, angle.headlines, brief, LIMITS["headline"], fallback=brief.one_liner)
            subhead = self._pick(rng, angle.subheads, brief, LIMITS["subhead"], fallback=brief.one_liner)
            # Control keeps the primary CTA; challengers rotate through the alternates.
            cta = brief.primary_cta if i == 0 or not brief.alt_ctas else brief.alt_ctas[(i - 1) % len(brief.alt_ctas)]
            order = tuple(s for s in angle.order if self._has(brief, s))
            out.append(
                Variant(
                    key=VARIANT_KEYS[i],
                    angle=angle.name,
                    headline=headline,
                    subhead=subhead,
                    cta=cta,
                    section_order=order,
                    hero_proof=angle.hero_proof(brief),
                    rationale=angle.why + ("" if i == 0 else f" CTA: \"{cta}\"."),
                    is_control=i == 0,
                )
            )
        return out

    @staticmethod
    def _pick(rng: random.Random, options, brief: Brief, limit: int, fallback: str) -> str:
        allowed = _numbers(brief.fact_text())
        candidates = []
        for make in options:
            try:
                text = " ".join(make(brief).split())
            except (IndexError, AttributeError):
                continue
            if text and len(text) <= limit and _numbers(text) <= allowed:
                candidates.append(text)
        if not candidates:
            return fallback[:limit]
        return candidates[rng.randrange(len(candidates))]

    @staticmethod
    def _has(brief: Brief, section: str) -> bool:
        return {
            "problem": bool(brief.pains),
            "how": bool(brief.steps),
            "proof": bool(brief.proof),
            "features": bool(brief.features),
            "testimonial": bool(brief.testimonials),
            "faq": bool(brief.faq),
            "cta": True,
        }[section]
