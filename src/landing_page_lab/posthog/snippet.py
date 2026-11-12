"""Build-time config + runtime script for flag-driven variant routing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Sequence

from ..variants import Variant

_KEY_OK = re.compile(r"^(phc_[A-Za-z0-9]+)?$")


@dataclass(frozen=True)
class SnippetConfig:
    flag_key: str
    variants: tuple[tuple[str, str, float], ...]  # (page key, flag value, weight)
    control: str
    primary_event: str
    api_key: str = ""                       # PostHog *project* key (public, write-only). Empty = local mode.
    api_host: str = "https://us.i.posthog.com"
    asset_host: str = "https://us-assets.i.posthog.com"
    base_path: str = "/"
    flag_timeout_ms: int = 1500
    enforce_assignment: bool = True

    def __post_init__(self) -> None:
        if not _KEY_OK.match(self.api_key):
            raise ValueError("api_key must be a PostHog project key (phc_...) or empty for local mode")
        for host in (self.api_host, self.asset_host):
            if not host.startswith("https://"):
                raise ValueError(f"PostHog hosts must be https, got {host!r}")
        if not self.base_path.startswith("/") or not self.base_path.endswith("/"):
            raise ValueError("base_path must start and end with '/'")

    def to_js_object(self) -> dict:
        return {
            "flagKey": self.flag_key,
            "variants": [{"key": k, "flag": f, "weight": w} for k, f, w in self.variants],
            "control": self.control,
            "primaryEvent": self.primary_event,
            "apiKey": self.api_key,
            "apiHost": self.api_host,
            "assetHost": self.asset_host,
            "basePath": self.base_path,
            "flagTimeoutMs": self.flag_timeout_ms,
            "enforceAssignment": self.enforce_assignment,
        }


def flag_value(v: Variant) -> str:
    """PostHog experiments require the control variant to be called "control"."""
    return "control" if v.is_control else v.key


def rollout(n: int) -> list[int]:
    """Integer percentages that sum to exactly 100 (PostHog rejects anything else)."""
    base, extra = divmod(100, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def config_for(flag_key: str, variants: Sequence[Variant], primary_event: str, **kw) -> SnippetConfig:
    control = next(v.key for v in variants if v.is_control)
    pct = rollout(len(variants))
    return SnippetConfig(flag_key, tuple((v.key, flag_value(v), float(p)) for v, p in zip(variants, pct)), control,
                         primary_event, **kw)


def runtime_js() -> str:
    return resources.files("landing_page_lab.posthog").joinpath("static/lpl.js").read_text(encoding="utf-8")


def head_tags(cfg: SnippetConfig, assets_prefix: str) -> str:
    """<script> tags to inject into <head>. JSON is escaped so it cannot close the tag."""
    payload = json.dumps(cfg.to_js_object(), separators=(",", ":")).replace("</", "<\\/")
    return (
        f'<script>window.LPL_CONFIG={payload};</script>\n'
        f'<script src="{assets_prefix}lpl.js"></script>'
    )
