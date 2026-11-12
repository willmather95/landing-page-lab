"""Vercel preview deploys via the REST API (files upload + create deployment).

Wired, not executed in this repo. Dry-run by default. Guards:
- never sends `target: "production"`; Vercel treats a deployment with no target as preview
- refuses any project listed in LPL_PROTECTED_PROJECTS
- live calls need LPL_DEPLOY_LIVE=1 and VERCEL_TOKEN
Endpoint shapes follow Vercel's public docs (POST /v2/files, POST /v13/deployments).
"""

from __future__ import annotations

import os
from pathlib import Path

from ..http import DryRunTransport, HttpError, HttpRequest, HttpResponse, Transport, UrllibTransport
from .base import DeployRefused, DeployResult, collect, live_enabled, protected_projects

API = "https://api.vercel.com"


def _dry(req: HttpRequest) -> HttpResponse:
    if req.url.startswith(f"{API}/v13/deployments"):
        return HttpResponse(200, {"id": "dpl_dryrun", "url": f"{req.json['name']}-dryrun.vercel.app", "readyState": "QUEUED"})
    return HttpResponse(200, {})


class VercelPreview:
    name = "vercel"

    def __init__(self, project: str, *, team_id: str | None = None, transport: Transport | None = None,
                 env: dict[str, str] | None = None):
        self.project = project
        self.team_id = team_id
        self._env = dict(os.environ if env is None else env)
        if project.lower() in protected_projects(self._env):
            raise DeployRefused(f"{project!r} is in LPL_PROTECTED_PROJECTS. Preview deploys never touch it.")
        if transport is not None:
            self.transport = transport
        elif live_enabled(self._env):
            if not self._env.get("VERCEL_TOKEN"):
                raise DeployRefused("LPL_DEPLOY_LIVE=1 but VERCEL_TOKEN is not set")
            self.transport = UrllibTransport()
        else:
            self.transport = DryRunTransport(_dry)
        self._token = self._env.get("VERCEL_TOKEN", "<VERCEL_TOKEN>")

    @property
    def dry_run(self) -> bool:
        return isinstance(self.transport, DryRunTransport)

    def _q(self) -> str:
        return f"?teamId={self.team_id}" if self.team_id else ""

    def build_requests(self, dist: Path) -> list[HttpRequest]:
        files = collect(dist)
        auth = {"Authorization": f"Bearer {self._token}"}
        reqs = [
            HttpRequest("POST", f"{API}/v2/files{self._q()}", headers={**auth, "Content-Type": "application/octet-stream",
                        "x-vercel-digest": f.sha1, "Content-Length": str(f.size)}, data=f.data, note=f.path)
            for f in files
        ]
        body = {
            "name": self.project,
            "files": [{"file": f.path, "sha": f.sha1, "size": f.size} for f in files],
            "projectSettings": {"framework": None, "buildCommand": None, "outputDirectory": None},
            "meta": {"source": "landing-page-lab"},
            # no "target": preview only, by construction
        }
        reqs.append(HttpRequest("POST", f"{API}/v13/deployments{self._q()}", headers=auth, json=body, note="create preview"))
        return reqs

    def deploy(self, dist: Path, variants: list[str]) -> DeployResult:
        reqs = self.build_requests(dist)
        assert all("target" not in (r.json or {}) for r in reqs), "production target must never be sent"
        last = None
        for r in reqs:
            last = self.transport.send(r)
            if not last.ok:
                raise HttpError(r, last)
        host = (last.body or {}).get("url", "")
        base = f"https://{host}/"
        log = tuple(r.redacted() for r in reqs)
        return DeployResult(self.name, self.dry_run, {"router": base, **{v: f"{base}{v}/" for v in variants}}, log,
                            note="dry run: nothing was sent" if self.dry_run else "preview deployment")
