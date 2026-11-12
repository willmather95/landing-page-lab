"""LLM-backed variant provider (Anthropic Messages API shape).

Wired as code, never called by the demo or the tests. It only sends a request when the
caller passes `allow_network=True` AND `ANTHROPIC_API_KEY` is set; otherwise it raises.
Output goes through the same copy guard as the offline provider, so a model cannot slip
an invented number onto the page.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

from ..brief import Brief
from ..http import DryRunTransport, HttpError, HttpRequest, Transport, UrllibTransport
from .provider import SECTIONS, VARIANT_KEYS, Variant

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = (
    "You write landing-page test variants. Each variant tests ONE angle. Use only facts and numbers "
    "from the brief; never invent a number, rating or result. Grade 8 reading level, short sentences, "
    "no hype words, no em dashes. Variant 'a' is the control and uses the primary CTA."
)

TOOL = {
    "name": "submit_variants",
    "description": "Return the landing-page variants.",
    "input_schema": {
        "type": "object",
        "properties": {
            "variants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "angle": {"type": "string"},
                        "headline": {"type": "string", "maxLength": 80},
                        "subhead": {"type": "string", "maxLength": 200},
                        "cta": {"type": "string", "maxLength": 32},
                        "section_order": {"type": "array", "items": {"type": "string", "enum": list(SECTIONS)}},
                        "hero_proof": {"type": ["string", "null"]},
                        "rationale": {"type": "string"},
                    },
                    "required": ["angle", "headline", "subhead", "cta", "section_order", "rationale"],
                },
            }
        },
        "required": ["variants"],
    },
}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, model: str = DEFAULT_MODEL, allow_network: bool = False, transport: Transport | None = None,
                 max_tokens: int = 2000):
        self.model = model
        self.allow_network = allow_network
        self.max_tokens = max_tokens
        self._transport = transport

    def build_request(self, brief: Brief, count: int, api_key: str = "<ANTHROPIC_API_KEY>") -> HttpRequest:
        brief_json = json.dumps(asdict(brief), indent=1, default=str)
        return HttpRequest(
            "POST",
            API_URL,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": SYSTEM,
                "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": "submit_variants"},
                "messages": [{"role": "user", "content": f"Write {count} variants for this brief:\n{brief_json}"}],
            },
        )

    def generate(self, brief: Brief, count: int) -> list[Variant]:
        transport = self._transport
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if transport is None or isinstance(transport, UrllibTransport):
            if not self.allow_network:
                raise RuntimeError("AnthropicProvider is network-only. Pass allow_network=True (and set ANTHROPIC_API_KEY), "
                                   "or use the default offline provider.")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            transport = transport or UrllibTransport(timeout=60)
        req = self.build_request(brief, count, key or "<ANTHROPIC_API_KEY>")
        resp = transport.send(req)
        if not resp.ok:
            raise HttpError(req, resp)
        return self.parse(resp.body, count)

    @staticmethod
    def parse(body: dict, count: int) -> list[Variant]:
        blocks = [b for b in (body or {}).get("content", []) if b.get("type") == "tool_use"]
        if not blocks:
            raise ValueError("model response has no tool_use block")
        raw = blocks[0]["input"].get("variants", [])[:count]
        if len(raw) < 2:
            raise ValueError("model returned fewer than two variants")
        return [
            Variant(
                key=VARIANT_KEYS[i], angle=str(v["angle"]), headline=str(v["headline"]).strip(),
                subhead=str(v["subhead"]).strip(), cta=str(v["cta"]).strip(),
                section_order=tuple(v["section_order"]), hero_proof=v.get("hero_proof"),
                rationale=str(v.get("rationale", "")), is_control=i == 0,
            )
            for i, v in enumerate(raw)
        ]


__all__ = ["AnthropicProvider", "DryRunTransport"]
