from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArmCounts:
    """Visitors exposed to one variant and how many of them converted."""

    name: str
    visitors: int
    conversions: int

    def __post_init__(self) -> None:
        if self.visitors < 0 or self.conversions < 0:
            raise ValueError(f"{self.name}: counts must be >= 0")
        if self.conversions > self.visitors:
            raise ValueError(f"{self.name}: conversions ({self.conversions}) > visitors ({self.visitors})")

    @property
    def rate(self) -> float:
        return self.conversions / self.visitors if self.visitors else 0.0
