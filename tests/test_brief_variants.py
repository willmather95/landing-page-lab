import copy

import pytest
import yaml

from landing_page_lab.brief import BriefError, parse_brief
from landing_page_lab.http import DryRunTransport, HttpResponse
from landing_page_lab.variants import OfflineProvider, Variant, check_variant, check_variants, generate_variants
from landing_page_lab.variants.llm import AnthropicProvider


@pytest.fixture()
def raw(brief_path):
    return yaml.safe_load(brief_path.read_text())


def test_example_brief_parses(brief):
    assert brief.product == "Fieldnote" and len(brief.proof) == 4 and brief.experiment.variants == 3
    assert brief.heading("how") == "Up and running the same day"
    assert brief.heading("problem") == "What it costs you today"  # default


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d["product"].pop("name"), "product.name"),
    (lambda d: d["experiment"].update(key="Bad Key"), "experiment.key"),
    (lambda d: d["experiment"].update(variants=9), "variants"),
    (lambda d: d.update(brand_color="blue"), "brand_color"),
    (lambda d: d["proof"].append(dict(d["proof"][0])), "unique"),
    (lambda d: d.update(headings={"hero": "x"}), "heading"),
    (lambda d: d["offer"].update(primary_cta="x" * 40), "max 32"),
])
def test_brief_validation(raw, mutate, msg):
    d = copy.deepcopy(raw)
    mutate(d)
    with pytest.raises(BriefError, match=msg):
        parse_brief(d)


def test_offline_is_deterministic_and_distinct(brief):
    a = generate_variants(brief)
    b = generate_variants(brief)
    assert a == b
    assert [v.key for v in a] == ["a", "b", "c"]
    assert [v.angle for v in a] == ["outcome", "pain", "proof"]
    assert a[0].is_control and a[0].cta == brief.primary_cta
    assert len({v.headline for v in a}) == 3
    assert len({v.section_order for v in a}) == 3
    assert all(v.section_order[-1] == "cta" for v in a)


def test_all_five_angles_pass_the_guard(brief):
    vs = OfflineProvider().generate(brief, 5)
    assert check_variants(brief, vs) == []


def test_changing_the_brief_changes_the_seed(brief, raw):
    d = copy.deepcopy(raw)
    d["product"]["one_liner"] = "Reminders your patients reply to"
    other = parse_brief(d)
    assert other.fingerprint() != brief.fingerprint()


def test_proof_angle_uses_a_second_stat_in_the_hero(brief):
    c = generate_variants(brief)[2]
    assert c.headline.startswith("31%") and c.hero_proof == "replies"


def _v(**kw):
    base = dict(key="b", angle="x", headline="Fine headline", subhead="Fine subhead", cta="Go",
                section_order=("how", "cta"), hero_proof=None, rationale="")
    base.update(kw)
    return Variant(**base)


@pytest.mark.parametrize("kw,needle", [
    ({"headline": "3x more bookings"}, "numbers not in the brief: 3"),
    ({"subhead": "A revolutionary way to book"}, "hype"),
    ({"headline": "Fast \u2014 and simple"}, "em dash"),
    ({"headline": "x" * 81}, "max 80"),
    ({"section_order": ("how",)}, "end with the cta"),
    ({"section_order": ("how", "how", "cta")}, "repeats"),
    ({"section_order": ("pricing", "cta")}, "unknown sections"),
    ({"hero_proof": "nope"}, "unknown proof id"),
    ({"cta": ""}, "empty"),
])
def test_guard_catches(brief, kw, needle):
    issues = check_variant(brief, _v(**kw))
    assert any(needle in i.message for i in issues), issues


def test_guard_allows_brief_numbers(brief):
    assert check_variant(brief, _v(headline="31% fewer no-shows in the first 60 days")) == []


def test_set_level_checks(brief):
    a = _v(key="a", is_control=True)
    issues = check_variants(brief, [a, _v(key="a")])
    msgs = " ".join(i.message for i in issues)
    assert "duplicate keys" in msgs and "share a headline" in msgs


def _tool_response(variants):
    return HttpResponse(200, {"content": [{"type": "tool_use", "name": "submit_variants", "input": {"variants": variants}}]})


def test_llm_provider_refuses_network_by_default(brief, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="network-only"):
        AnthropicProvider().generate(brief, 3)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(allow_network=True).generate(brief, 3)


def test_llm_provider_request_shape_and_parse(brief):
    good = [
        {"angle": "outcome", "headline": "A full schedule, fewer calls", "subhead": "Reminders patients answer.",
         "cta": "Start a 14-day trial", "section_order": ["how", "proof", "cta"], "rationale": "control"},
        {"angle": "pain", "headline": "Stop chasing no-shows", "subhead": "Two-way texts.", "cta": "Get my reminder setup",
         "section_order": ["problem", "how", "cta"], "rationale": "pain"},
    ]
    t = DryRunTransport(lambda req: _tool_response(good))
    vs = generate_variants(brief, AnthropicProvider(transport=t), count=2)
    assert [v.key for v in vs] == ["a", "b"] and vs[0].is_control
    body = t.requests[0].json
    assert body["tool_choice"] == {"type": "tool", "name": "submit_variants"}
    assert body["model"].startswith("claude-")
    assert t.requests[0].redacted()["headers"]["x-api-key"] == "<redacted>"


def test_llm_output_with_invented_number_is_rejected(brief):
    bad = [
        {"angle": "outcome", "headline": "Book 3x more patients", "subhead": "s", "cta": "Go", "section_order": ["cta"], "rationale": ""},
        {"angle": "pain", "headline": "Other", "subhead": "s", "cta": "Go", "section_order": ["cta"], "rationale": ""},
    ]
    t = DryRunTransport(lambda req: _tool_response(bad))
    with pytest.raises(ValueError, match="numbers not in the brief"):
        generate_variants(brief, AnthropicProvider(transport=t), count=2)
