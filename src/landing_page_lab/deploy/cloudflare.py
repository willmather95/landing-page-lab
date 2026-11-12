"""Cloudflare Pages preview deploys (direct upload), mirroring wrangler's request sequence.

Wired, not executed in this repo. Dry-run by default. Guards:
- deploys to a preview branch (`lpl-<experiment>`), and refuses the production branch
- refuses any project listed in LPL_PROTECTED_PROJECTS
- live calls need LPL_DEPLOY_LIVE=1, CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID

Caveat: wrangler keys assets by a BLAKE3 hash, which the Python stdlib lacks. The default
`asset_hash` here is a truncated SHA-256, fine for dry runs. Pass a BLAKE3-based
`asset_hash` before going live.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Callable

from ..http import DryRunTransport, HttpError, HttpRequest, HttpResponse, Transport, UrllibTransport
from .base import DeployRefused, DeployResult, SiteFile, collect, live_enabled, protected_projects

API = "https://api.cloudflare.com/client/v4"


def sha256_asset_hash(f: SiteFile) -> str:
    ext = f.path.rsplit(".", 1)[-1] if "." in f.path else ""
    return hashlib.sha256(base64.b64encode(f.data) + ext.encode()).hexdigest()[:32]


def _dry(req: HttpRequest) -> HttpResponse:
    if req.url.endswith("/upload-token"):
        return HttpResponse(200, {"success": True, "result": {"jwt": "<UPLOAD_JWT>"}})
    if req.url.endswith("/check-missing"):
        return HttpResponse(200, {"success": True, "result": req.json["hashes"]})
    if req.url.endswith("/deployments"):
        return HttpResponse(200, {"success": True, "result": {"id": "dryrun", "url": "https://dryrun.example.pages.dev"}})
    return HttpResponse(200, {"success": True, "result": None})


class CloudflarePagesPreview:
    name = "cloudflare-pages"

    def __init__(self, project: str, branch: str, *, production_branch: str = "main", transport: Transport | None = None,
                 env: dict[str, str] | None = None, asset_hash: Callable[[SiteFile], str] = sha256_asset_hash):
        self._env = dict(os.environ if env is None else env)
        if project.lower() in protected_projects(self._env):
            raise DeployRefused(f"{project!r} is in LPL_PROTECTED_PROJECTS. Preview deploys never touch it.")
        if branch in (production_branch, "main", "master", "production"):
            raise DeployRefused(f"branch {branch!r} would publish to production. Use a preview branch.")
        self.project, self.branch, self.asset_hash = project, branch, asset_hash
        if transport is not None:
            self.transport = transport
        elif live_enabled(self._env):
            if not (self._env.get("CLOUDFLARE_API_TOKEN") and self._env.get("CLOUDFLARE_ACCOUNT_ID")):
                raise DeployRefused("LPL_DEPLOY_LIVE=1 but CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID missing")
            self.transport = UrllibTransport()
        else:
            self.transport = DryRunTransport(_dry)
        self._token = self._env.get("CLOUDFLARE_API_TOKEN", "<CLOUDFLARE_API_TOKEN>")
        self._account = self._env.get("CLOUDFLARE_ACCOUNT_ID", "<ACCOUNT_ID>")

    @property
    def dry_run(self) -> bool:
        return isinstance(self.transport, DryRunTransport)

    def _send(self, req: HttpRequest, log: list[dict]) -> HttpResponse:
        log.append(req.redacted())
        resp = self.transport.send(req)
        if not resp.ok or not (resp.body or {}).get("success", False):
            raise HttpError(req, resp)
        return resp

    def deploy(self, dist: Path, variants: list[str]) -> DeployResult:
        files = collect(dist)
        hashes = {f.path: self.asset_hash(f) for f in files}
        log: list[dict] = []
        proj = f"{API}/accounts/{self._account}/pages/projects/{self.project}"
        auth = {"Authorization": f"Bearer {self._token}"}
        jwt = self._send(HttpRequest("GET", f"{proj}/upload-token", headers=auth), log).body["result"]["jwt"]
        jauth = {"Authorization": f"Bearer {jwt}"}
        missing = set(self._send(HttpRequest("POST", f"{API}/pages/assets/check-missing", headers=jauth,
                                             json={"hashes": sorted(set(hashes.values()))}), log).body["result"])
        payload = [
            {"key": hashes[f.path], "value": base64.b64encode(f.data).decode(), "base64": True,
             "metadata": {"contentType": mimetypes.guess_type(f.path)[0] or "application/octet-stream"}}
            for f in files if hashes[f.path] in missing
        ]
        if payload:
            self._send(HttpRequest("POST", f"{API}/pages/assets/upload", headers=jauth, json=payload,
                                   note=f"{len(payload)} assets"), log)
        self._send(HttpRequest("POST", f"{API}/pages/assets/upsert-hashes", headers=jauth,
                               json={"hashes": sorted(set(hashes.values()))}), log)
        manifest = {"/" + p: h for p, h in hashes.items()}
        body, ctype = _multipart({"manifest": json.dumps(manifest), "branch": self.branch})
        resp = self._send(HttpRequest("POST", f"{proj}/deployments", headers={**auth, "Content-Type": ctype}, data=body,
                                      note=f"deployment on preview branch {self.branch}"), log)
        base = resp.body["result"]["url"].rstrip("/") + "/"
        return DeployResult(self.name, self.dry_run, {"router": base, **{v: f"{base}{v}/" for v in variants}}, tuple(log),
                            note="dry run: nothing was sent" if self.dry_run else f"preview branch {self.branch}")


def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode(), f"multipart/form-data; boundary={boundary}"
