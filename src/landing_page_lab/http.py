"""One tiny HTTP layer for every outside API (PostHog, Vercel, Cloudflare, LLM).

Adapters build `HttpRequest` objects and hand them to a `Transport`. The default is
`DryRunTransport`, which records and prints requests and returns canned responses, so
the whole pipeline runs offline. `UrllibTransport` makes real calls and is only built
when the caller passes explicit live settings.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TextIO

SENSITIVE = {"authorization", "x-api-key", "x-auth-key", "x-auth-email", "cookie"}


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    json: Any = None
    data: bytes | None = None
    note: str = ""

    def redacted(self) -> dict[str, Any]:
        headers = {k: ("<redacted>" if k.lower() in SENSITIVE else v) for k, v in self.headers.items()}
        out: dict[str, Any] = {"method": self.method, "url": self.url, "headers": headers}
        if self.json is not None:
            out["json"] = self.json
        if self.data is not None:
            out["data"] = f"<{len(self.data)} bytes>"
        if self.note:
            out["note"] = self.note
        return out


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpError(RuntimeError):
    def __init__(self, request: HttpRequest, response: HttpResponse):
        super().__init__(f"{request.method} {request.url} -> HTTP {response.status}: {str(response.body)[:300]}")
        self.request = request
        self.response = response


class Transport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


Responder = Callable[[HttpRequest], HttpResponse]


class DryRunTransport:
    """Records requests instead of sending them. Optionally prints each one."""

    def __init__(self, responder: Responder | None = None, *, echo: bool = False, stream: TextIO | None = None):
        self.requests: list[HttpRequest] = []
        self._responder = responder or (lambda req: HttpResponse(200, {"dry_run": True}))
        self._echo = echo
        self._stream = stream or sys.stdout

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self._echo:
            print(f"[dry-run] {request.method} {request.url}", file=self._stream)
            if request.json is not None:
                print(json.dumps(request.json, indent=2), file=self._stream)
        return self._responder(request)

    def log(self) -> list[dict[str, Any]]:
        return [r.redacted() for r in self.requests]


class UrllibTransport:
    """Real HTTP. Only constructed by code paths that already passed a live-mode guard."""

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def send(self, request: HttpRequest) -> HttpResponse:
        body = request.data
        headers = dict(request.headers)
        if request.json is not None:
            body = json.dumps(request.json).encode()
            headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(request.url, data=body, method=request.method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (https only, see adapters)
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            parsed: Any = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw.decode(errors="replace")
        return HttpResponse(status, parsed)
