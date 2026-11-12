from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SiteFile:
    path: str          # relative, forward slashes
    data: bytes

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.data).hexdigest()  # noqa: S324 (content digest required by Vercel, not security)

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class DeployResult:
    adapter: str
    dry_run: bool
    urls: dict[str, str]                          # variant key -> preview URL
    requests: tuple[dict, ...] = field(default_factory=tuple)
    note: str = ""


class PreviewAdapter(Protocol):
    name: str

    def deploy(self, dist: Path, variants: list[str]) -> DeployResult: ...


class DeployRefused(RuntimeError):
    pass


def collect(dist: Path) -> list[SiteFile]:
    dist = Path(dist)
    if not (dist / "manifest.json").exists():
        raise FileNotFoundError(f"{dist} has no manifest.json. Run `lpl build` first.")
    files = []
    for p in sorted(dist.rglob("*")):
        if p.is_file():
            files.append(SiteFile(p.relative_to(dist).as_posix(), p.read_bytes()))
    return files


def protected_projects(env: dict[str, str] | None = None) -> set[str]:
    env = os.environ if env is None else env
    return {x.strip().lower() for x in env.get("LPL_PROTECTED_PROJECTS", "").split(",") if x.strip()}


def live_enabled(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get("LPL_DEPLOY_LIVE") == "1"
