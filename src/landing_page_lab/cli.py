"""lpl: landing-page-lab command line. Every command runs offline with zero credentials."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__


def _parse_rates(text: str) -> dict[str, float]:
    out = {}
    for part in text.split(","):
        k, v = part.split("=")
        out[k.strip()] = float(v)
    return out


def _parse_counts(text: str) -> dict[str, tuple[int, int]]:
    out = {}
    for part in text.split(","):
        k, v = part.split("=")
        n, c = v.split("/")
        out[k.strip()] = (int(n), int(c))
    return out


def cmd_generate(a) -> int:
    from .brief import load_brief
    from .variants import generate_variants

    vs = generate_variants(load_brief(a.brief), count=a.count)
    if a.json:
        print(json.dumps([v.to_dict() for v in vs], indent=2))
    else:
        for v in vs:
            tag = " (control)" if v.is_control else ""
            print(f"[{v.key}] {v.angle}{tag}\n  headline: {v.headline}\n  subhead:  {v.subhead}\n  cta:      {v.cta}\n"
                  f"  sections: {' > '.join(v.section_order)}\n  why:      {v.rationale}\n")
    return 0


def cmd_build(a) -> int:
    import os

    from .brief import load_brief
    from .posthog.snippet import config_for
    from .site.build import build_site
    from .variants import generate_variants

    b = load_brief(a.brief)
    vs = generate_variants(b, count=a.count)
    key = os.environ.get("POSTHOG_PROJECT_API_KEY", "") if a.posthog else ""
    res = build_site(b, vs, a.out, snippet=config_for(b.experiment.key, vs, b.experiment.primary_event, api_key=key))
    print(f"built {len(res.variants)} variants into {res.dist}/ ({'posthog' if key else 'local'} mode)")
    for rel in res.files:
        print(f"  {rel}")
    return 0


def cmd_plan(a) -> int:
    from .api import create_experiment

    h = create_experiment(a.brief, out_dir=a.out, build=False)
    print(h.plan.note)
    print(f"looks on days: {', '.join(map(str, h.plan.look_days))}\n")
    print("PostHog requests (dry run, nothing sent):")
    print(json.dumps(list(h.posthog.requests), indent=2))
    return 0


def cmd_preview(a) -> int:
    from .deploy import LocalPreview

    manifest = json.loads((Path(a.dist) / "manifest.json").read_text())
    keys = [v["key"] for v in manifest["variants"]]
    with LocalPreview(port=a.port) as lp:
        res = lp.deploy(Path(a.dist), keys)
        for k, u in res.urls.items():
            print(f"{k:>7}  {u}")
        print("Ctrl-C to stop. Add ?lpl_variant=<key> to force a variant.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_deploy(a) -> int:
    from .deploy import CloudflarePagesPreview, VercelPreview

    manifest = json.loads((Path(a.dist) / "manifest.json").read_text())
    keys = [v["key"] for v in manifest["variants"]]
    if a.adapter == "vercel":
        ad = VercelPreview(a.project)
    else:
        ad = CloudflarePagesPreview(a.project, a.branch or f"lpl-{manifest['experiment']}")
    res = ad.deploy(Path(a.dist), keys)
    print(json.dumps({"adapter": res.adapter, "dry_run": res.dry_run, "note": res.note, "urls": res.urls,
                      "requests": [{k: v for k, v in r.items() if k != "json"} for r in res.requests]}, indent=2))
    return 0


def cmd_simulate(a) -> int:
    from .simulate import TrueArm, simulate_traffic, to_csv

    rates = _parse_rates(a.rates)
    w = [float(x) for x in a.weights.split(",")] if a.weights else [1.0] * len(rates)
    arms = [TrueArm(k, r, wt) for (k, r), wt in zip(rates.items(), w)]
    text = to_csv(simulate_traffic(arms, days=a.days, daily_visitors=a.daily, seed=a.seed))
    if a.out:
        Path(a.out).write_text(text)
        print(f"wrote {a.out} (SIMULATED)")
    else:
        sys.stdout.write(text)
    return 0


def cmd_readout(a) -> int:
    from .readout import Policy, readout
    from .simulate import cumulative, from_csv

    if a.csv:
        rows = from_csv(Path(a.csv).read_text())
        order = list(dict.fromkeys(r.arm for r in rows))
        day = a.day if a.day is not None else max(r.day for r in rows)
        counts = cumulative(rows, day, order)
    elif a.counts:
        counts, day = _parse_counts(a.counts), a.day
    else:
        print("need --csv or --counts", file=sys.stderr)
        return 2
    weights = [float(x) for x in a.weights.split(",")] if a.weights else None
    looks = tuple(int(x) for x in a.looks.split(",")) if a.looks else Policy().look_days
    r = readout(counts, control=a.control, weights=weights, day=day, policy=Policy(look_days=looks))
    print(r.to_json() if a.json else r.to_markdown())
    return 0


def cmd_calibrate(a) -> int:
    from .calibrate import calibrate, to_markdown

    res, secs = calibrate(seeds=a.seeds)
    md = to_markdown(res, secs)
    print(md)
    if a.out:
        Path(a.out).write_text(md)
    return 0


def cmd_demo(a) -> int:
    from .demo import run_demo

    res = run_demo(a.brief, a.out, docs=a.docs, seed=a.seed, images=not a.no_images)
    print(f"variants:  {', '.join(f'{v.key} ({v.angle})' for v in res.handle.variants)}")
    print(f"built:     {res.handle.build.dist if res.handle.build else '-'}")
    print(f"plan:      {res.handle.plan.note}")
    print(f"posthog:   {len(res.handle.posthog.requests)} requests written to {res.out / 'posthog-requests.json'} (dry run)")
    print(f"readout:   {res.headline}  [{res.out / 'readout.md'}]")
    print(f"images:    {', '.join(map(str, res.images)) or 'skipped (no Chrome found or --no-images)'}")
    print("SIMULATED traffic. No real visitors, no network calls.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lpl", description=__doc__)
    p.add_argument("--version", action="version", version=f"landing-page-lab {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("generate", help="brief -> variants (offline provider)")
    s.add_argument("brief"); s.add_argument("--count", type=int); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("build", help="brief -> dist/<variant>/ static sites + router")
    s.add_argument("brief"); s.add_argument("--out", default="dist"); s.add_argument("--count", type=int)
    s.add_argument("--posthog", action="store_true", help="inject POSTHOG_PROJECT_API_KEY from env (else local mode)")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("plan", help="traffic plan + PostHog experiment/flag requests (dry run)")
    s.add_argument("brief"); s.add_argument("--out", default="out/plan")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("preview", help="serve a build on 127.0.0.1")
    s.add_argument("dist", nargs="?", default="dist"); s.add_argument("--port", type=int, default=8787)
    s.set_defaults(fn=cmd_preview)

    s = sub.add_parser("deploy", help="preview deploy requests for Vercel / Cloudflare Pages (dry run unless LPL_DEPLOY_LIVE=1)")
    s.add_argument("dist"); s.add_argument("--adapter", choices=["vercel", "cloudflare"], required=True)
    s.add_argument("--project", required=True); s.add_argument("--branch")
    s.set_defaults(fn=cmd_deploy)

    s = sub.add_parser("simulate", help="SIMULATED daily traffic with known true rates -> CSV")
    s.add_argument("--rates", default="a=0.04,b=0.042,c=0.048"); s.add_argument("--weights")
    s.add_argument("--days", type=int, default=21); s.add_argument("--daily", type=int, default=2000)
    s.add_argument("--seed", type=int, default=42); s.add_argument("--out")
    s.set_defaults(fn=cmd_simulate)

    s = sub.add_parser("readout", help="decide: winner / keep running / no winner / invalid")
    s.add_argument("--csv"); s.add_argument("--counts", help="a=9000/360,b=9000/400")
    s.add_argument("--day", type=int); s.add_argument("--control"); s.add_argument("--weights")
    s.add_argument("--looks", help="planned look days, default 7,14,21"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_readout)

    s = sub.add_parser("calibrate", help="many-seed check that the readout recovers known truths")
    s.add_argument("--seeds", type=int, default=300); s.add_argument("--out")
    s.set_defaults(fn=cmd_calibrate)

    s = sub.add_parser("demo", help="brief -> 3 variants -> 21 simulated days -> readout + hero chart")
    s.add_argument("--brief", default="examples/brief.yaml"); s.add_argument("--out", default="out/demo")
    s.add_argument("--docs", default=None, help="write hero.png and screenshots here (needs Chrome)")
    s.add_argument("--seed", type=int, default=42); s.add_argument("--no-images", action="store_true")
    s.set_defaults(fn=cmd_demo)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
