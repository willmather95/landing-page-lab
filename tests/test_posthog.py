import pytest

from landing_page_lab.http import DryRunTransport, HttpError, HttpResponse, UrllibTransport
from landing_page_lab.posthog.client import LiveConfig, LiveModeRefused, PostHogClient
from landing_page_lab.variants import generate_variants

LIVE_ENV = {"LPL_POSTHOG_LIVE": "1", "POSTHOG_HOST": "https://ph.example", "POSTHOG_PROJECT_ID": "11",
            "POSTHOG_SANDBOX_PROJECT_ID": "11", "POSTHOG_PERSONAL_API_KEY": "placeholder"}


@pytest.fixture()
def variants(brief):
    return generate_variants(brief)


def test_experiment_payload_shape(variants):
    p = PostHogClient.experiment_payload("exp-1", variants, primary_event="lpl_signup", relative_mde=0.2)
    fv = p["parameters"]["feature_flag_variants"]
    assert [v["key"] for v in fv] == ["control", "b", "c"]
    assert sum(v["rollout_percentage"] for v in fv) == 100
    assert p["start_date"] is None and p["feature_flag_key"] == "exp-1"
    assert p["metrics"][0]["series"][0]["event"] == "lpl_signup"


def test_flag_filters_shape(variants):
    f = PostHogClient.flag_filters(variants)
    assert f["groups"] == [{"properties": [], "rollout_percentage": 100}]
    assert [v["rollout_percentage"] for v in f["multivariate"]["variants"]] == [34, 33, 33]


def test_dry_run_create_sequence_and_redaction(variants):
    c = PostHogClient.dry_run()
    created = c.create_experiment("exp-1", variants, primary_event="lpl_signup", relative_mde=0.2)
    methods = [(r["method"], r["url"].split("/api/projects/<PROJECT_ID>/")[1]) for r in created.requests]
    assert methods == [("GET", "feature_flags/?search=exp-1"), ("POST", "experiments/"), ("PATCH", "feature_flags/0/")]
    assert all(r["headers"]["Authorization"] == "<redacted>" for r in created.requests)
    assert c.is_dry_run


def test_never_reuses_an_existing_flag(variants):
    t = DryRunTransport(lambda req: HttpResponse(200, {"results": [{"key": "exp-1", "id": 5}]}))
    c = PostHogClient("https://ph.example", "1", transport=t)
    with pytest.raises(RuntimeError, match="already exists"):
        c.create_experiment("exp-1", variants, primary_event="lpl_signup", relative_mde=0.2)
    assert len(t.requests) == 1  # stopped before any write


def test_http_errors_surface(variants):
    t = DryRunTransport(lambda req: HttpResponse(403, {"detail": "nope"}))
    with pytest.raises(HttpError, match="403"):
        PostHogClient("https://ph.example", "1", transport=t).find_flag("exp-1")


def test_fetch_counts_maps_flag_values_to_page_keys(variants):
    rows = [["control", 1000, 40], ["b", 990, 45], ["c", 1010, 52]]
    t = DryRunTransport(lambda req: HttpResponse(200, {"results": rows}))
    c = PostHogClient("https://ph.example", "1", transport=t)
    counts = c.fetch_counts("exp-1", variants, event="lpl_signup", start="2026-11-01", end="2026-11-22")
    assert [(a.name, a.visitors, a.conversions) for a in counts] == [("a", 1000, 40), ("b", 990, 45), ("c", 1010, 52)]
    q = t.requests[0].json["query"]
    assert q["kind"] == "HogQLQuery" and q["values"]["flag"] == "exp-1"
    assert "exp-1" not in q["query"]  # values are passed as placeholders, not spliced


def test_unsafe_keys_are_rejected():
    with pytest.raises(ValueError):
        PostHogClient.counts_query("x' OR 1=1 --", "lpl_signup", "a", "b")


def test_live_mode_guards():
    with pytest.raises(LiveModeRefused, match="LPL_POSTHOG_LIVE"):
        LiveConfig.from_env({})
    with pytest.raises(LiveModeRefused, match="missing"):
        LiveConfig.from_env({"LPL_POSTHOG_LIVE": "1"})
    with pytest.raises(LiveModeRefused, match="sandbox"):
        LiveConfig.from_env({**LIVE_ENV, "POSTHOG_SANDBOX_PROJECT_ID": "99"})
    with pytest.raises(LiveModeRefused, match="https"):
        LiveConfig.from_env({**LIVE_ENV, "POSTHOG_HOST": "http://ph.example"})
    client = PostHogClient.live(LIVE_ENV)  # builds, but sends nothing until called
    assert isinstance(client.transport, UrllibTransport) and not client.is_dry_run
