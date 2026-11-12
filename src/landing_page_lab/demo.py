"""`make demo`: brief -> 3 variants built -> 21 days of SIMULATED traffic -> readout + hero chart."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .api import ExperimentHandle, create_experiment
from .chart import HeroData, hero_html
from .render_chrome import find_chrome, screenshot
from .simulate import TrueArm, run_sequential, simulate_traffic, to_csv

DEMO_RATES = {"a": 0.040, "b": 0.042, "c": 0.048}
DEMO_SEED = 42


@dataclass(frozen=True)
class DemoResult:
    handle: ExperimentHandle
    out: Path
    headline: str
    decision_day: int
    images: tuple[Path, ...]


def run_demo(brief_path: str | Path, out: str | Path = "out/demo", *, docs: str | Path | None = None,
             seed: int = DEMO_SEED, images: bool = True) -> DemoResult:
    out = Path(out)
    handle = create_experiment(brief_path, out_dir=out)
    keys = [v.key for v in handle.variants]
    truth = tuple(TrueArm(k, DEMO_RATES.get(k, 0.04), w) for k, w in zip(keys, handle.weights))
    policy = handle.policy()
    days = policy.look_days[-1]
    rows = simulate_traffic(truth, days=days, daily_visitors=handle.brief.experiment.daily_visitors, seed=seed)
    run = run_sequential(truth, policy=policy, rows=rows, detail=True, seed=seed)

    (out / "traffic.csv").write_text(to_csv(rows))
    md = [run.final.to_markdown(title=f"Readout: {handle.key} (SIMULATED)")]
    md.append("## Every planned look\n")
    md.append("| Day | Status | Leader | P(best) | Boundary |z| |")
    md.append("|---:|---|---|---:|---:|")
    for r in run.history:
        md.append(f"| {r.day} | `{r.status.value}` | {r.leader} | {r.arm(r.leader).prob_best:.1%} | {r.boundary_z:.2f} |")
    md.append("")
    md.append(f"Simulation: true rates {', '.join(f'{a.name} {a.rate:.1%}' for a in truth)}; "
              f"{handle.brief.experiment.daily_visitors:,} visitors a day before weekday swings; seed {seed}. "
              "These are made-up visitors, not real traffic.\n")
    (out / "readout.md").write_text("\n".join(md))
    (out / "readout.json").write_text(json.dumps({
        "simulated": True, "seed": seed, "true_rates": DEMO_RATES, "decision_day": run.decision_day,
        "history": [h.to_dict() for h in run.history],
    }, indent=2, default=str) + "\n")
    hero = hero_html(HeroData(tuple(rows), truth, run, seed, days))
    (out / "hero.html").write_text(hero)

    made: list[Path] = []
    if images and docs is not None and find_chrome():
        docs = Path(docs)
        if screenshot((out / "hero.html").resolve().as_uri(), docs / "hero.png", width=1600, height=900, scale=1.5):
            made.append(docs / "hero.png")
        dist = handle.build.dist if handle.build else out / "dist"
        for v in handle.variants:
            p = docs / f"variant-{v.key}.png"
            if screenshot((dist / v.key / "index.html").resolve().as_uri(), p, width=1280, height=1500):
                made.append(p)
        sheet = out / "variants.html"
        sheet.write_text(_contact_sheet(handle, docs))
        if screenshot(sheet.resolve().as_uri(), docs / "variants.png", width=1600, height=900, scale=1.5):
            made.append(docs / "variants.png")
    return DemoResult(handle, out, run.final.headline(), run.decision_day, tuple(made))


def _contact_sheet(handle: ExperimentHandle, docs: Path) -> str:
    from html import escape as e

    cols = "".join(
        f'<figure><div class="cap"><b>{e(v.key)}</b> &middot; {e(v.angle)}{" (control)" if v.is_control else ""}</div>'
        f'<img src="{(docs / f"variant-{v.key}.png").resolve().as_uri()}"><figcaption>{e(v.headline)}</figcaption></figure>'
        for v in handle.variants
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}} html,body{{width:1600px;height:900px}}
body{{background:#f2f2f1;font-family:"Geist",system-ui,sans-serif;color:#141414;padding:44px 48px}}
h1{{font-size:28px;letter-spacing:-.02em}} p{{color:#6b6b6b;margin-top:6px;font-size:16px}}
.g{{display:grid;grid-template-columns:repeat({len(handle.variants)},1fr);gap:28px;margin-top:26px}}
figure{{background:#fff;border-radius:20px;padding:16px;box-shadow:0 8px 24px -12px rgba(0,0,0,.1)}}
.cap{{font-size:16px;margin-bottom:12px;color:#3f3f3f}} img{{width:100%;height:560px;object-fit:cover;object-position:top;border-radius:10px;border:1px solid #e4e4e3}}
figcaption{{font-size:14px;color:#6b6b6b;margin-top:10px;line-height:1.4}}
</style></head><body><h1>Three variants from one brief</h1>
<p>Same design system, different angle, headline, CTA and section order. Built by <code>make demo</code> from examples/brief.yaml (fictional product).</p>
<div class="g">{cols}</div></body></html>"""


__all__ = ["DEMO_RATES", "DEMO_SEED", "DemoResult", "run_demo"]
