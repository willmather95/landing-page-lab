import dataclasses
import hashlib
import json
import re
import urllib.request

import pytest

from landing_page_lab.deploy import LocalPreview
from landing_page_lab.posthog.snippet import SnippetConfig, config_for, rollout
from landing_page_lab.site.build import build_site
from landing_page_lab.variants import generate_variants


@pytest.fixture()
def built(brief, tmp_path):
    vs = generate_variants(brief)
    return build_site(brief, vs, tmp_path / "dist"), vs


def test_build_layout_and_manifest(built):
    res, vs = built
    for rel in ("index.html", "a/index.html", "b/index.html", "c/index.html", "assets/site.css", "assets/lpl.js"):
        assert (res.dist / rel).is_file()
    m = json.loads(res.manifest_path.read_text())
    assert m["mode"] == "local" and [v["key"] for v in m["variants"]] == ["a", "b", "c"]
    for rel, digest in m["files"].items():
        assert hashlib.sha256((res.dist / rel).read_bytes()).hexdigest() == digest


def test_each_page_has_its_own_copy_and_section_order(built):
    res, vs = built
    for v in vs:
        html = (res.dist / v.key / "index.html").read_text()
        assert f"<h1>{v.headline}</h1>" in html.replace("&#x27;", "'")
        assert f'content="{v.key}"' in html
        ids = re.findall(r'<section class="(?:block|cta)" id="(\w+)"', html)
        expected = ["signup" if s == "cta" else s for s in v.section_order]
        assert ids == expected
        assert f"window.lpl.page(\"{v.key}\")" in html
        assert "../assets/site.css" in html and "../assets/lpl.js" in html


def test_router_carries_flag_config(built, brief):
    res, _ = built
    html = (res.dist / "index.html").read_text()
    cfg = json.loads(re.search(r"window.LPL_CONFIG=(\{.*?\});</script>", html).group(1))
    assert cfg["flagKey"] == brief.experiment.key
    assert [v["flag"] for v in cfg["variants"]] == ["control", "b", "c"]
    assert sum(v["weight"] for v in cfg["variants"]) == 100
    assert cfg["apiKey"] == "" and "lpl.route()" in html


def test_brief_text_is_escaped(brief, tmp_path):
    evil = dataclasses.replace(brief, product="<script>alert(1)</script>", disclaimer='"><img src=x onerror=alert(1)>')
    vs = generate_variants(brief)
    res = build_site(evil, vs, tmp_path / "d")
    html = (res.dist / "a" / "index.html").read_text()
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_config_json_cannot_close_the_script_tag(brief, tmp_path):
    vs = generate_variants(brief)
    cfg = config_for("k", vs, "evt</script><script>alert(1)</script>")
    res = build_site(brief, vs, tmp_path / "d", snippet=cfg)
    html = (res.dist / "index.html").read_text()
    assert "evt</script>" not in html and "evt<\\/script>" in html


def test_refuses_to_clean_a_foreign_directory(brief, tmp_path):
    d = tmp_path / "precious"
    d.mkdir()
    (d / "keep.txt").write_text("mine")
    with pytest.raises(RuntimeError, match="refusing to clean"):
        build_site(brief, generate_variants(brief), d)
    assert (d / "keep.txt").exists()


def test_rebuild_over_previous_build_is_fine(brief, tmp_path):
    vs = generate_variants(brief)
    build_site(brief, vs, tmp_path / "d")
    build_site(brief, vs, tmp_path / "d")


def test_snippet_config_validation():
    with pytest.raises(ValueError):
        SnippetConfig("k", (("a", "control", 100.0),), "a", "e", api_key="sk-not-a-project-key")
    with pytest.raises(ValueError):
        SnippetConfig("k", (("a", "control", 100.0),), "a", "e", api_host="http://insecure")
    assert rollout(3) == [34, 33, 33] and sum(rollout(7)) == 100


def test_local_preview_serves_every_variant(built):
    res, vs = built
    with LocalPreview() as lp:
        out = lp.deploy(res.dist, [v.key for v in vs])
        for v in vs:
            with urllib.request.urlopen(out.urls[v.key], timeout=5) as r:
                body = r.read().decode()
                assert r.status == 200 and f'name="lpl-variant" content="{v.key}"' in body
                assert r.headers["X-Robots-Tag"] == "noindex"
        with urllib.request.urlopen(out.urls["router"] + "assets/lpl.js", timeout=5) as r:
            assert b"window.lpl" in r.read()


def test_local_preview_is_loopback_only():
    with pytest.raises(ValueError):
        LocalPreview(host="0.0.0.0")
