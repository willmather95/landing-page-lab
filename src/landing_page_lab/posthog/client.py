"""PostHog REST client: experiment + feature flag creation, launch, and result counts.

Default is dry-run: requests are built with the real endpoint paths and payload shapes,
recorded and printed, and canned responses come back. Live calls need ALL of:

    LPL_POSTHOG_LIVE=1
    POSTHOG_HOST=https://...            (your instance, https only)
    POSTHOG_PROJECT_ID=<id>
    POSTHOG_SANDBOX_PROJECT_ID=<same id> (you assert this project is a sandbox)
    POSTHOG_PERSONAL_API_KEY=<key>       (scoped to that project)

Payload shapes follow PostHog's public REST docs (projects/:id/experiments,
feature_flags, query). They have not been run against a live project from this repo,
so try them in a sandbox project before trusting them.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Sequence

from ..http import DryRunTransport, HttpError, HttpRequest, HttpResponse, Transport, UrllibTransport
from ..stats import ArmCounts
from ..variants import Variant
from .snippet import flag_value, rollout

_SAFE = re.compile(r"^[A-Za-z0-9_$.:-]{1,100}$")


class LiveModeRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveConfig:
    host: str
    project_id: str
    api_key: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "LiveConfig":
        env = dict(os.environ if env is None else env)
        if env.get("LPL_POSTHOG_LIVE") != "1":
            raise LiveModeRefused("live PostHog calls are off. Set LPL_POSTHOG_LIVE=1 to opt in.")
        missing = [k for k in ("POSTHOG_HOST", "POSTHOG_PROJECT_ID", "POSTHOG_SANDBOX_PROJECT_ID", "POSTHOG_PERSONAL_API_KEY") if not env.get(k)]
        if missing:
            raise LiveModeRefused(f"missing env: {', '.join(missing)}")
        if env["POSTHOG_PROJECT_ID"] != env["POSTHOG_SANDBOX_PROJECT_ID"]:
            raise LiveModeRefused("POSTHOG_PROJECT_ID is not the declared sandbox project. Refusing.")
        if not env["POSTHOG_HOST"].startswith("https://"):
            raise LiveModeRefused("POSTHOG_HOST must be https")
        return cls(env["POSTHOG_HOST"].rstrip("/"), env["POSTHOG_PROJECT_ID"], env["POSTHOG_PERSONAL_API_KEY"])


def _dry_responder(req: HttpRequest) -> HttpResponse:
    if req.method == "GET" and "/feature_flags/" in req.url:
        return HttpResponse(200, {"results": []})
    if req.method == "POST" and req.url.endswith("/experiments/"):
        key = req.json["feature_flag_key"]
        return HttpResponse(201, {"id": 0, "name": req.json["name"], "feature_flag": {"id": 0, "key": key}, "start_date": None})
    if req.method == "PATCH":
        return HttpResponse(200, {"id": 0, **(req.json or {})})
    if req.url.endswith("/query/"):
        return HttpResponse(200, {"columns": ["variant", "visitors", "conversions"], "results": []})
    return HttpResponse(200, {"dry_run": True})


@dataclass(frozen=True)
class CreatedExperiment:
    experiment_id: Any
    flag_id: Any
    flag_key: str
    requests: tuple[dict, ...]


class PostHogClient:
    def __init__(self, host: str, project_id: str, *, transport: Transport, api_key: str = "<POSTHOG_PERSONAL_API_KEY>"):
        self.host = host.rstrip("/")
        self.project_id = project_id
        self.transport = transport
        self._api_key = api_key

    @classmethod
    def dry_run(cls, *, echo: bool = False, host: str = "https://us.posthog.com", project_id: str = "<PROJECT_ID>") -> "PostHogClient":
        return cls(host, project_id, transport=DryRunTransport(_dry_responder, echo=echo))

    @classmethod
    def live(cls, env: dict[str, str] | None = None) -> "PostHogClient":
        cfg = LiveConfig.from_env(env)
        return cls(cfg.host, cfg.project_id, transport=UrllibTransport(), api_key=cfg.api_key)

    @property
    def is_dry_run(self) -> bool:
        return isinstance(self.transport, DryRunTransport)

    # ---- payloads -------------------------------------------------------------------------
    @staticmethod
    def flag_filters(variants: Sequence[Variant]) -> dict:
        pct = rollout(len(variants))
        return {
            "groups": [{"properties": [], "rollout_percentage": 100}],
            "multivariate": {
                "variants": [
                    {"key": flag_value(v), "name": f"{v.key}: {v.angle}" + (" (control)" if v.is_control else ""), "rollout_percentage": p}
                    for v, p in zip(variants, pct)
                ]
            },
        }

    @staticmethod
    def experiment_payload(flag_key: str, variants: Sequence[Variant], *, primary_event: str, relative_mde: float,
                           description: str = "") -> dict:
        _check(flag_key, "flag key")
        _check(primary_event, "event")
        pct = rollout(len(variants))
        return {
            "name": f"{flag_key}: landing page test",
            "description": description or "Created by landing-page-lab. Readout: Bayesian + group-sequential z-test.",
            "feature_flag_key": flag_key,
            "type": "product",
            "start_date": None,  # draft; launch is a separate, explicit call
            "parameters": {
                "feature_flag_variants": [{"key": flag_value(v), "rollout_percentage": p} for v, p in zip(variants, pct)],
                "minimum_detectable_effect": round(relative_mde * 100, 2),
            },
            "metrics": [
                {
                    "kind": "ExperimentMetric",
                    "metric_type": "funnel",
                    "series": [{"kind": "EventsNode", "event": primary_event}],
                }
            ],
        }

    # ---- calls ------------------------------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.host}/api/projects/{self.project_id}/{path}"

    def _send(self, method: str, path: str, body: Any = None, note: str = "") -> HttpResponse:
        req = HttpRequest(method, self._url(path), headers={"Authorization": f"Bearer {self._api_key}"}, json=body, note=note)
        resp = self.transport.send(req)
        if not resp.ok:
            raise HttpError(req, resp)
        return resp

    def find_flag(self, key: str) -> dict | None:
        _check(key, "flag key")
        resp = self._send("GET", f"feature_flags/?search={key}", note="does the flag already exist?")
        for f in (resp.body or {}).get("results", []):
            if f.get("key") == key:
                return f
        return None

    def create_experiment(self, flag_key: str, variants: Sequence[Variant], *, primary_event: str, relative_mde: float) -> CreatedExperiment:
        """Create a DRAFT experiment (PostHog creates the linked flag), then pin exact flag rollout."""
        if self.find_flag(flag_key):
            raise RuntimeError(f"flag {flag_key!r} already exists. Pick a new experiment key; never reuse a live flag.")
        body = self.experiment_payload(flag_key, variants, primary_event=primary_event, relative_mde=relative_mde)
        exp = self._send("POST", "experiments/", body, note="draft experiment, creates the linked multivariate flag").body
        flag_id = (exp.get("feature_flag") or {}).get("id")
        self._send(
            "PATCH", f"feature_flags/{flag_id}/",
            {"filters": self.flag_filters(variants), "ensure_experience_continuity": False},
            note="pin variant names and exact rollout on the experiment's flag",
        )
        log = tuple(self.transport.log()) if isinstance(self.transport, DryRunTransport) else ()
        return CreatedExperiment(exp.get("id"), flag_id, flag_key, log)

    def launch(self, experiment_id: Any, start_date: str) -> dict:
        """Start collecting. Separate on purpose: creation never starts traffic."""
        return self._send("PATCH", f"experiments/{experiment_id}/", {"start_date": start_date}, note="launch").body

    @staticmethod
    def counts_query(flag_key: str, event: str, start: str, end: str) -> dict:
        _check(flag_key, "flag key")
        _check(event, "event")
        sql = (
            "SELECT e.variant AS variant, count() AS visitors, countIf(c.converted_at >= e.first_seen) AS conversions "
            "FROM (SELECT person_id, argMin(properties.$feature_flag_response, timestamp) AS variant, min(timestamp) AS first_seen "
            "FROM events WHERE event = '$feature_flag_called' AND properties.$feature_flag = {flag} "
            "AND timestamp >= toDateTime({start}) AND timestamp < toDateTime({end}) GROUP BY person_id) AS e "
            "LEFT JOIN (SELECT person_id, min(timestamp) AS converted_at FROM events WHERE event = {event} "
            "AND timestamp >= toDateTime({start}) AND timestamp < toDateTime({end}) GROUP BY person_id) AS c "
            "ON e.person_id = c.person_id GROUP BY variant ORDER BY variant"
        )
        return {"query": {"kind": "HogQLQuery", "query": sql, "values": {"flag": flag_key, "event": event, "start": start, "end": end}}}

    def fetch_counts(self, flag_key: str, variants: Sequence[Variant], *, event: str, start: str, end: str) -> list[ArmCounts]:
        """Unique exposed persons and converters per variant, mapped back to page keys."""
        body = self._send("POST", "query/", self.counts_query(flag_key, event, start, end), note="experiment counts").body or {}
        by_flag = {str(r[0]): (int(r[1]), int(r[2])) for r in body.get("results", [])}
        return [ArmCounts(v.key, *by_flag.get(flag_value(v), (0, 0))) for v in variants]


def _check(value: str, what: str) -> None:
    if not _SAFE.match(value):
        raise ValueError(f"unsafe {what}: {value!r}")
