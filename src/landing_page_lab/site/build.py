"""Build every variant into dist/<key>/index.html plus a flag-driven router at dist/index.html."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Sequence

from ..brief import Brief
from ..posthog.snippet import SnippetConfig, config_for, head_tags, runtime_js
from ..variants import Variant
from . import render


@dataclass(frozen=True)
class BuildResult:
    dist: Path
    files: dict[str, str]  # relative path -> sha256
    variants: tuple[str, ...]

    @property
    def manifest_path(self) -> Path:
        return self.dist / "manifest.json"


def _css() -> str:
    return resources.files("landing_page_lab.site").joinpath("static/site.css").read_text(encoding="utf-8")


def build_site(
    brief: Brief,
    variants: Sequence[Variant],
    dist: str | Path,
    *,
    snippet: SnippetConfig | None = None,
    clean: bool = True,
) -> BuildResult:
    dist = Path(dist)
    if clean and dist.exists():
        if not (dist / "manifest.json").exists() and any(dist.iterdir()):
            raise RuntimeError(f"refusing to clean {dist}: it is not empty and has no manifest.json from a previous build")
        shutil.rmtree(dist)
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    cfg = snippet or config_for(brief.experiment.key, variants, brief.experiment.primary_event)

    written: dict[str, bytes] = {}

    def put(rel: str, text: str) -> None:
        data = text.encode("utf-8")
        path = dist / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written[rel] = data

    put("assets/site.css", _css())
    put("assets/lpl.js", runtime_js())
    for v in variants:
        put(f"{v.key}/index.html", render.page(brief, v, head_extra=head_tags(cfg, "../assets/"),
                                               assets_prefix="../assets/", experiment_key=brief.experiment.key))
    put("index.html", render.router(brief, head_extra=head_tags(cfg, "assets/"),
                                    variant_links=[(f"{v.key}/", f"{v.key}: {v.headline}") for v in variants]))
    files = {rel: hashlib.sha256(data).hexdigest() for rel, data in sorted(written.items())}
    manifest = {
        "experiment": brief.experiment.key,
        "brief_fingerprint": brief.fingerprint()[:16],
        "mode": "posthog" if cfg.api_key else "local",
        "variants": [v.to_dict() for v in variants],
        "files": files,
    }
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return BuildResult(dist, files, tuple(v.key for v in variants))
