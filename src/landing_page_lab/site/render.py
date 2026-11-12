"""HTML for one variant. Plain functions, every brief string escaped."""

from __future__ import annotations

from html import escape as e

from ..brief import Brief
from ..variants import Variant


def _sup(brief: Brief, proof_id: str) -> str:
    idx = [p.id for p in brief.proof].index(proof_id) + 1
    return f'<sup><a href="#src-{idx}">[{idx}]</a></sup>'


def hero(brief: Brief, v: Variant) -> str:
    if v.hero_proof:
        p = next(x for x in brief.proof if x.id == v.hero_proof)
        side = (
            f'<aside class="chip" aria-label="Key result"><div class="stat">{e(p.stat)}{_sup(brief, p.id)}</div>'
            f'<div class="label">{e(p.label)}</div><div class="src">Source: {e(p.source)}</div></aside>'
        )
    else:
        cells = "".join(f'<span class="{c}"></span>' for c in ("ok", "ok", "x", "ok", "", "ok", "", "ok", "ok", "x"))
        side = (
            f'<aside class="chip" aria-label="Illustration"><div class="cal" aria-hidden="true">{cells}</div>'
            f'<div class="cal-cap">Illustration only. Striped slots are the gaps this page is about.</div></aside>'
        )
    return f"""
<header class="hero">
  <div>
    <div class="eyebrow">{e(brief.category)}</div>
    <h1>{e(v.headline)}</h1>
    <p class="sub">{e(v.subhead)}</p>
    <a class="btn" href="#signup" data-lpl-cta="hero">{e(v.cta)} <span aria-hidden="true">&rarr;</span></a>
    <div class="risk">{e(brief.risk_reversal)}</div>
  </div>
  {side}
</header>"""


def problem(brief: Brief, v: Variant) -> str:
    items = "".join(f"<li>{e(p)}</li>" for p in brief.pains)
    return f'<section class="block" id="problem"><div class="eyebrow">Sound familiar?</div><h2>{e(brief.heading('problem'))}</h2><ul class="pains">{items}</ul></section>'


def how(brief: Brief, v: Variant) -> str:
    items = "".join(f"<li><h3>{e(s.title)}</h3><p>{e(s.body)}</p></li>" for s in brief.steps)
    return f'<section class="block" id="how"><div class="eyebrow">How it works</div><h2>{e(brief.heading('how'))}</h2><ol class="steps">{items}</ol></section>'


def proof(brief: Brief, v: Variant) -> str:
    items = "".join(f"<div><b>{e(p.stat)}{_sup(brief, p.id)}</b><span>{e(p.label)}</span></div>" for p in brief.proof)
    return f'<section class="block" id="proof"><div class="eyebrow">Results</div><h2>{e(brief.heading('proof'))}</h2><div class="stats">{items}</div></section>'


def features(brief: Brief, v: Variant) -> str:
    items = "".join(f"<div><h3>{e(f.title)}</h3><p>{e(f.body)}</p></div>" for f in brief.features)
    return f'<section class="block" id="features"><div class="eyebrow">Features</div><h2>{e(brief.heading('features'))}</h2><div class="features">{items}</div></section>'


def testimonial(brief: Brief, v: Variant) -> str:
    t = brief.testimonials[0]
    return (
        f'<section class="block" id="testimonial"><blockquote>&ldquo;{e(t.quote)}&rdquo;'
        f'<footer>{e(t.name)}, {e(t.role)}</footer></blockquote></section>'
    )


def faq(brief: Brief, v: Variant) -> str:
    items = "".join(f"<details><summary>{e(f.q)}</summary><p>{e(f.a)}</p></details>" for f in brief.faq)
    return f'<section class="block" id="faq"><div class="eyebrow">Questions</div><h2>{e(brief.heading('faq'))}</h2>{items}</section>'


def cta(brief: Brief, v: Variant) -> str:
    return f"""
<section class="cta" id="signup">
  <div><h2>{e(brief.outcome[:1].upper() + brief.outcome[1:])}</h2><p>{e(brief.risk_reversal)}</p></div>
  <div>
    <form class="signup" data-lpl-form="signup">
      <label class="sr" for="email" style="position:absolute;left:-9999px">Work email</label>
      <input id="email" type="email" name="email" placeholder="you@clinic.example" required autocomplete="email">
      <button class="btn" type="submit" data-lpl-cta="form">{e(v.cta)}</button>
    </form>
    <div class="thanks" role="status">Thanks. This is a demo page, so nothing was sent.</div>
  </div>
</section>"""


SECTION_RENDERERS = {
    "problem": problem, "how": how, "proof": proof, "features": features,
    "testimonial": testimonial, "faq": faq, "cta": cta,
}


def page(brief: Brief, v: Variant, *, head_extra: str, assets_prefix: str, experiment_key: str) -> str:
    body = "\n".join(SECTION_RENDERERS[s](brief, v) for s in v.section_order)
    sources = "".join(f'<li id="src-{i}">{e(p.stat)} {e(p.label)}: {e(p.source)}</li>' for i, p in enumerate(brief.proof, 1))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(brief.product)}: {e(v.headline)}</title>
<meta name="description" content="{e(v.subhead)}">
<meta name="robots" content="noindex">
<meta name="lpl-variant" content="{e(v.key)}">
<meta name="lpl-experiment" content="{e(experiment_key)}">
<link rel="stylesheet" href="{assets_prefix}site.css">
<style>:root{{--brand:{e(brief.brand_color)}}}</style>
{head_extra}
</head>
<body>
<div class="wrap">
<nav class="nav"><div class="logo"><i aria-hidden="true"></i>{e(brief.product)}</div><a class="small" href="#signup" data-lpl-cta="nav">{e(v.cta)}</a></nav>
{hero(brief, v)}
{body}
<footer class="foot">
  <div>{e(brief.disclaimer)}</div>
  <ol>{sources}</ol>
  <div class="meta">experiment {e(experiment_key)} &middot; variant {e(v.key)} ({e(v.angle)})</div>
</footer>
</div>
<script>window.lpl && window.lpl.page({_js_str(v.key)});</script>
</body>
</html>
"""


def router(brief: Brief, *, head_extra: str, variant_links: list[tuple[str, str]]) -> str:
    links = "".join(f'<li><a href="{e(href)}">{e(label)}</a></li>' for href, label in variant_links)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{e(brief.product)}</title>
{head_extra}
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;background:#f6f5f2;color:#3f3f3f}}</style>
</head>
<body>
<main><p>Loading&hellip;</p><noscript><p>Pick a version:</p><ul>{links}</ul></noscript></main>
<script>window.lpl && window.lpl.route();</script>
</body>
</html>
"""


def _js_str(s: str) -> str:
    import json

    return json.dumps(s).replace("</", "<\\/")
