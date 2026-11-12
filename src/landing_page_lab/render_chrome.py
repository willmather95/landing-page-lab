"""Headless Chrome screenshots (used for docs/ images). Optional: skipped if no browser."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")


def find_chrome() -> str | None:
    env = os.environ.get("LPL_CHROME")
    if env and Path(env).exists():
        return env
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def screenshot(url: str, out: Path, *, width: int, height: int, scale: float = 1.0, chrome: str | None = None) -> bool:
    chrome = chrome or find_chrome()
    if not chrome:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    # Note: a custom --user-data-dir makes some headless Chrome builds hang on exit, so we use the default.
    cmd = [
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        "--disable-extensions", "--allow-file-access-from-files",
        f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
        "--virtual-time-budget=2500", f"--screenshot={out.resolve()}", url,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return False
    return res.returncode == 0 and out.exists()
