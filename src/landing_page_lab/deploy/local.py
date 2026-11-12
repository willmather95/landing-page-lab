"""LocalPreview: serve dist/ on 127.0.0.1. The only adapter that actually runs."""

from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .base import DeployResult, collect


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep test output clean
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        super().end_headers()


class LocalPreview:
    name = "local"

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("LocalPreview binds to loopback only")
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def deploy(self, dist: Path, variants: list[str]) -> DeployResult:
        collect(dist)  # validates it is a build
        handler = functools.partial(_QuietHandler, directory=str(Path(dist).resolve()))
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        base = f"http://{self.host}:{self.port}/"
        urls = {"router": base, **{v: f"{base}{v}/" for v in variants}}
        return DeployResult(self.name, False, urls, note="serving from this machine only")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "LocalPreview":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
