"""Run the browser runtime (lpl.js) in Node with a tiny fake DOM: bucketing, flag mapping, routing."""

import json
import shutil
import subprocess

import pytest

from landing_page_lab.posthog.snippet import runtime_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HARNESS = r"""
const src = process.argv[1];
const cfg = JSON.parse(process.argv[2]);
const search = process.argv[3] || "";
function makeWindow(id) {
  const store = new Map(id ? [["lpl_id", id]] : []);
  const replaced = [];
  const win = {
    LPL_CONFIG: cfg,
    location: { search, hash: "", replace: (u) => replaced.push(u) },
    console: { info() {} },
    crypto: { randomUUID: () => "uuid-" + Math.random() },
  };
  const ls = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
  const document = { addEventListener() {}, createElement() { return {}; }, head: { appendChild() {} } };
  new Function("window", "localStorage", "document", "location", "URLSearchParams", "setTimeout", "crypto", "console",
    src)(win, ls, document, win.location, URLSearchParams, setTimeout, win.crypto, win.console);
  return { win, replaced, store };
}
const counts = {};
for (let i = 0; i < 30000; i++) {
  const { win } = makeWindow("visitor-" + i);
  const k = win.lpl._bucket();
  counts[k] = (counts[k] || 0) + 1;
}
const sticky = makeWindow("same-visitor");
const first = sticky.win.lpl._bucket();
const again = sticky.win.lpl._bucket();
const routed = makeWindow("visitor-7");
routed.win.lpl.route();
const ev = makeWindow("ev");
ev.win.lpl.page("b");
ev.win.lpl.capture("lpl_signup", { form: "signup" });
console.log(JSON.stringify({
  counts, sticky: first === again,
  fromFlag: [routed.win.lpl._fromFlag("control"), routed.win.lpl._fromFlag("c"), routed.win.lpl._fromFlag("zzz")],
  routedTo: routed.replaced, expected: routed.win.lpl._bucket(),
  events: JSON.parse(ev.store.get("lpl_events")),
}));
"""


def run(cfg, search=""):
    out = subprocess.run([NODE, "-e", HARNESS, runtime_js(), json.dumps(cfg), search],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


CFG = {"flagKey": "exp", "control": "a", "primaryEvent": "lpl_signup", "apiKey": "", "apiHost": "https://x",
       "assetHost": "https://x", "basePath": "/", "flagTimeoutMs": 50, "enforceAssignment": True,
       "variants": [{"key": "a", "flag": "control", "weight": 34}, {"key": "b", "flag": "b", "weight": 33},
                    {"key": "c", "flag": "c", "weight": 33}]}


def test_local_bucketing_matches_weights_and_is_sticky():
    r = run(CFG)
    total = sum(r["counts"].values())
    for key, w in (("a", 0.34), ("b", 0.33), ("c", 0.33)):
        assert abs(r["counts"][key] / total - w) < 0.015
    assert r["sticky"]


def test_flag_values_map_back_to_page_keys():
    assert run(CFG)["fromFlag"] == ["a", "c", None]


def test_router_sends_visitor_to_their_bucket():
    r = run(CFG)
    assert r["routedTo"] == [f"/{r['expected']}/"]


def test_forced_variant_wins_and_is_stripped_from_url():
    r = run(CFG, "?lpl_variant=c&utm_source=x")
    assert r["routedTo"] == ["/c/?utm_source=x"]


def test_events_carry_the_feature_property():
    r = run(CFG)
    ev = [e for e in r["events"] if e["event"] == "lpl_signup"][0]
    assert ev["props"]["$feature/exp"] == "b" and ev["props"]["lpl_variant"] == "b"
