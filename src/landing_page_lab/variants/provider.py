from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from ..brief import Brief

SECTIONS = ("problem", "how", "proof", "features", "testimonial", "faq", "cta")
VARIANT_KEYS = ("a", "b", "c", "d", "e")


@dataclass(frozen=True)
class Variant:
    key: str
    angle: str
    headline: str
    subhead: str
    cta: str
    section_order: tuple[str, ...]
    hero_proof: str | None
    rationale: str
    is_control: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Variant":
        return cls(
            key=str(d["key"]), angle=str(d["angle"]), headline=str(d["headline"]), subhead=str(d["subhead"]),
            cta=str(d["cta"]), section_order=tuple(d["section_order"]), hero_proof=d.get("hero_proof"),
            rationale=str(d.get("rationale", "")), is_control=bool(d.get("is_control", False)),
        )


class VariantProvider(Protocol):
    name: str

    def generate(self, brief: Brief, count: int) -> list[Variant]: ...


def generate_variants(brief: Brief, provider: VariantProvider | None = None, count: int | None = None) -> list[Variant]:
    """Generate and guard-check variants. Raises if any variant breaks the copy rules."""
    from .guard import check_variants
    from .offline import OfflineProvider

    provider = provider or OfflineProvider()
    n = count or brief.experiment.variants
    variants = provider.generate(brief, n)
    issues = check_variants(brief, variants)
    if issues:
        msg = "\n".join(f"- {i.variant}: {i.field}: {i.message}" for i in issues)
        raise ValueError(f"{provider.name} produced copy that breaks the brief rules:\n{msg}")
    return variants
