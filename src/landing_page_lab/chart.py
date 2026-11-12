"""Hero chart: cumulative conversion by variant with the looks and the call, plus posteriors.

Plain SVG + HTML, styled with the world-class-charts token values (light theme). Every
number on it comes from the demo run passed in. Rendered to PNG by headless Chrome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape as e
from typing import Sequence

from .readout import Readout, Status
from .simulate import DayCount, SequentialRun, TrueArm, cumulative
from .stats.bayes import posteriors

INK, INK2, MUTED = "#141414", "#3f3f3f", "#6b6b6b"
GRID, HAIR, AXIS = "#ececeb", "#e4e4e3", "#8a8a8a"
ACCENT, ACCENT_SOFT, ACCENT_INK = "#0a72e8", "#d8e8fc", "#0657b8"
POS_INK, WARN_INK = "#0b6e34", "#8a5300"
QUIET = ("#8c8c8c", "#b0aca6", "#6f6a64", "#c2bdb5")


@dataclass(frozen=True)
class HeroData:
    rows: tuple[DayCount, ...]
    truth: tuple[TrueArm, ...]
    run: SequentialRun
    seed: int
    days: int


def _nice_ticks(lo: float, hi: float, step: float) -> list[float]:
    start = math.floor(lo / step) * step
    out, v = [], start
    while v <= hi + 1e-12:
        if v >= lo - 1e-12:
            out.append(round(v, 10))
        v += step
    return out


def _colors(names: Sequence[str], highlight: str | None) -> dict[str, str]:
    out, q = {}, iter(QUIET)
    for n in names:
        out[n] = ACCENT if n == highlight else next(q)
    return out


def cumulative_svg(d: HeroData, w: int = 600, h: int = 420) -> str:
    names = [a.name for a in d.truth]
    final = d.run.final
    hl = final.winner or final.leader
    col = _colors(names, hl)
    series: dict[str, list[tuple[int, float]]] = {n: [] for n in names}
    for day in range(1, d.days + 1):
        for arm in cumulative(d.rows, day, names):
            if arm.visitors:
                series[arm.name].append((day, arm.rate))
    vals = [r for s in series.values() for _, r in s if _ > 2] + [a.rate for a in d.truth]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad
    ml, mr, mt, mb = 48, 92, 46, 34
    pw, ph = w - ml - mr, h - mt - mb

    def x(day: float) -> float:
        return ml + (day - 1) / (d.days - 1) * pw

    def y(r: float) -> float:
        return mt + (1 - (r - lo) / (hi - lo)) * ph

    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Cumulative conversion rate by variant">']
    # post-decision shading
    if final.status is Status.WINNER and d.run.decision_day < d.days:
        x0 = x(d.run.decision_day)
        parts.append(f'<rect x="{x0:.1f}" y="{mt}" width="{ml + pw - x0:.1f}" height="{ph}" fill="#f6f6f5"/>')
        parts.append(f'<text x="{(x0 + ml + pw) / 2:.1f}" y="{mt + ph - 10}" text-anchor="middle" font-size="12" fill="{MUTED}">after the call</text>')
    step = 0.005 if hi - lo > 0.012 else 0.0025
    for t in _nice_ticks(lo, hi, step):
        parts.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>')
        parts.append(f'<text x="{ml - 8}" y="{y(t) + 4:.1f}" text-anchor="end" font-size="12" fill="{MUTED}">{t * 100:.1f}%</text>')
    for day in (1, 7, 14, 21):
        if day <= d.days:
            parts.append(f'<text x="{x(day):.1f}" y="{h - 10}" text-anchor="middle" font-size="12" fill="{MUTED}">Day {day}</text>')
    # look markers
    for r in d.run.history:
        xd = x(r.day or 0)
        call = r.status is Status.WINNER
        color = POS_INK if call else WARN_INK
        label = f"Winner: {r.winner}" if call else ("No winner" if r.status is Status.NO_WINNER else "Keep running")
        parts.append(f'<line x1="{xd:.1f}" x2="{xd:.1f}" y1="{mt - 6}" y2="{mt + ph}" stroke="{color}" stroke-dasharray="3 4" stroke-width="1.5"/>')
        parts.append(f'<text x="{xd:.1f}" y="{mt - 26}" text-anchor="middle" font-size="12.5" font-weight="600" fill="{color}">Look {(r.look or 0) + 1}</text>')
        parts.append(f'<text x="{xd:.1f}" y="{mt - 11}" text-anchor="middle" font-size="12.5" fill="{color}">{e(label)}</text>')
    # true rates (faint) and lines; highlight drawn last
    order = [n for n in names if n != hl] + [hl]
    for n in order:
        pts = series[n]
        if not pts:
            continue
        path = "M" + " L".join(f"{x(dd):.1f},{y(r):.1f}" for dd, r in pts)
        width = 3 if n == hl else 2
        parts.append(f'<path d="{path}" fill="none" stroke="{col[n]}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')
    # direct labels at line ends, nudged apart
    ends = sorted(((series[n][-1][1], n) for n in names if series[n]), reverse=True)
    placed: list[float] = []
    for rate, n in ends:
        yy = y(rate)
        for p in placed:
            if abs(yy - p) < 17:
                yy = p + 17
        placed.append(yy)
        truth = next(a.rate for a in d.truth if a.name == n)
        weight = "700" if n == hl else "500"
        parts.append(f'<text x="{ml + pw + 8}" y="{yy + 4:.1f}" font-size="13" font-weight="{weight}" fill="{col[n] if n == hl else INK2}">{e(n)} {rate * 100:.2f}%</text>')
        parts.append(f'<text x="{ml + pw + 8}" y="{yy + 18:.1f}" font-size="11" fill="{MUTED}">true {truth * 100:.1f}%</text>')
        placed[-1] = yy + 14
    parts.append("</svg>")
    return "".join(parts)


def posterior_svg(r: Readout, w: int = 260, h: int = 420) -> str:
    from .stats import ArmCounts

    arms = [ArmCounts(a.name, a.visitors, a.conversions) for a in r.arms]
    posts = posteriors(arms)
    hl = r.winner or r.leader
    col = _colors([p.name for p in posts], hl)
    lo = min(p.mean - 4.5 * p.sd for p in posts)
    hi = max(p.mean + 4.5 * p.sd for p in posts)
    n = 160
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    dens = {p.name: [math.exp(p.logpdf(v)) for v in xs] for p in posts}
    top = max(max(v) for v in dens.values())
    ml, mr, mt, mb = 10, 10, 46, 34
    pw, ph = w - ml - mr, h - mt - mb

    def X(v: float) -> float:
        return ml + (v - lo) / (hi - lo) * pw

    def Y(v: float) -> float:
        return mt + ph - v / top * (ph - 40)

    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Posterior distributions">']
    parts.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="{AXIS}"/>')
    for t in _nice_ticks(lo, hi, 0.005):
        parts.append(f'<text x="{X(t):.1f}" y="{h - 10}" text-anchor="middle" font-size="12" fill="{MUTED}">{t * 100:.1f}%</text>')
    labels: list[tuple[float, float]] = []
    for p in sorted(posts, key=lambda q: q.name == hl):
        ys = dens[p.name]
        line = " L".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(xs, ys))
        fill = ACCENT_SOFT if p.name == hl else "none"
        op = "0.85" if p.name == hl else "1"
        parts.append(f'<path d="M{X(xs[0]):.1f},{mt + ph} L{line} L{X(xs[-1]):.1f},{mt + ph} Z" fill="{fill}" fill-opacity="{op}" stroke="none"/>')
        parts.append(f'<path d="M{line}" fill="none" stroke="{col[p.name]}" stroke-width="{2.5 if p.name == hl else 1.75}"/>')
        peak = max(range(n), key=lambda i: ys[i])
        row = next(a for a in r.arms if a.name == p.name)
        weight = "700" if p.name == hl else "500"
        lx, ly = X(xs[peak]), Y(ys[peak]) - 8
        for ox, oy in labels:  # stack labels that would overlap
            if abs(lx - ox) < 48 and abs(ly - oy) < 16:
                ly = oy - 17
        labels.append((lx, ly))
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="12.5" font-weight="{weight}" fill="{col[p.name] if p.name == hl else INK2}">{e(p.name)} · {row.prob_best:.0%}</text>')
    parts.append(f'<text x="{ml}" y="{mt - 26}" font-size="12.5" font-weight="600" fill="{INK2}">Posterior on day {r.day}</text>')
    parts.append(f'<text x="{ml}" y="{mt - 11}" font-size="12.5" fill="{MUTED}">label = P(best)</text>')
    parts.append("</svg>")
    return "".join(parts)


def hero_html(d: HeroData, *, repo: str = "github.com/willmather95/landing-page-lab") -> str:
    r = d.run.final
    total = sum(a.visitors for a in r.arms)
    win = r.arm(r.winner) if r.winner else None
    if win and win.lift is not None and win.lift_ci:
        lift_val = f"{win.lift * 100:+.1f}%"
        lift_sub = f"95% interval {win.lift_ci[0] * 100:+.0f}% to {win.lift_ci[1] * 100:+.0f}%"
    else:
        lift_val, lift_sub = "n/a", "no winner called"
    call = f"{r.winner}" if r.winner else "none"
    call_sub = f"day {d.run.decision_day} of {d.days}, look {(r.look or 0) + 1}" if r.winner else r.status.value.replace("_", " ")
    pbest = f"{win.prob_best * 100:.1f}%" if win else f"{r.arm(r.leader).prob_best * 100:.1f}%"
    truth = ", ".join(f"{a.name} {a.rate * 100:.1f}%" for a in d.truth)
    stats = [
        ("Visitors at the call", f"{total:,}", f"{len(r.arms)} variants, simulated"),
        ("Winner", call, call_sub),
        ("Lift vs control", lift_val, lift_sub),
        ("P(best)", pbest, "needs 95% plus a sequential z-test"),
    ]
    cells = "".join(
        f'<div class="s"><div class="k">{e(k)}</div><div class="v">{e(v)}</div><div class="u">{e(u)}</div></div>' for k, v, u in stats
    )
    if r.winner:
        held = [h.day for h in d.run.history[:-1]]
        if held:
            when = " and ".join(f"day {x}" for x in held) if len(held) <= 2 else ", ".join(f"day {x}" for x in held)
            sub = (f"{r.winner} led most days. The readout said keep running at {when}, then called it on day "
                   f"{d.run.decision_day}, when both tests agreed.")
        else:
            sub = f"{r.winner} was called at the first look, day {d.run.decision_day}, when both tests agreed."
    else:
        sub = "No variant cleared both tests, so the readout keeps control."
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
html,body{{width:1600px;height:900px}}
body{{background:#f2f2f1;color:{INK};font-family:"Geist","Inter",system-ui,sans-serif;padding:56px;display:grid;grid-template-columns:480px 1fr;gap:48px}}
.l{{display:flex;flex-direction:column}}
.repo{{font:500 17px/1 "Geist Mono",ui-monospace,monospace;color:{MUTED}}}
h1{{font-size:56px;line-height:1.04;letter-spacing:-.03em;margin-top:30px;font-weight:700}}
.lede{{font-size:23px;line-height:1.42;color:{INK2};margin-top:24px}}
.foot{{margin-top:auto;font-size:15.5px;line-height:1.5;color:{MUTED}}}
.foot b{{color:{INK2};font-weight:600}}
.card{{background:#fff;border-radius:24px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 24px -12px rgba(0,0,0,.08);padding:26px 30px}}
.r{{display:flex;flex-direction:column;gap:22px}}
.strip{{display:grid;grid-template-columns:repeat(4,1fr)}}
.s{{padding:0 20px;border-left:1px solid {HAIR}}} .s:first-child{{padding-left:0;border-left:0}}
.k{{font-size:15px;color:{MUTED}}} .v{{font-size:38px;font-weight:700;letter-spacing:-.025em;margin-top:8px}} .u{{font-size:13.5px;color:{MUTED};margin-top:6px}}
.t{{font-size:21px;font-weight:600}} .st{{font-size:15.5px;color:{MUTED};margin-top:6px}}
.charts{{display:flex;gap:18px;margin-top:6px;align-items:flex-start}}
.src{{font-size:13px;color:{MUTED};margin-top:4px}}
svg text{{font-family:"Geist","Inter",system-ui,sans-serif}}
</style></head><body>
<div class="l">
  <div class="repo">{e(repo)}</div>
  <h1>Calls a winner only when both tests agree.</h1>
  <p class="lede">Brief in, three landing-page variants built, a PostHog experiment planned, and a readout that says
  &ldquo;keep running&rdquo; until a Bayesian test and a sequential z-test both clear their bars.</p>
  <div class="foot"><b>SIMULATED traffic.</b> {d.days} days of made-up visitors with known true rates ({e(truth)}), seed {d.seed}.
  Produced by <b>make demo</b>. No real visitors, no PostHog calls.</div>
</div>
<div class="r">
  <div class="card"><div class="strip">{cells}</div></div>
  <div class="card">
    <div class="t">Cumulative conversion rate by variant</div>
    <div class="st">{e(sub)}</div>
    <div class="charts">{cumulative_svg(d)}{posterior_svg(r)}</div>
    <div class="src">Source: out/demo/readout.md and traffic.csv from this repo's demo run.</div>
  </div>
</div>
</body></html>"""
