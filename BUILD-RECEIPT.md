# BUILD RECEIPT: landing-page-lab

Built Nov 12, 2026 to the bar in COMMON.md and the landing-page-lab spec. Local repo only: nothing was pushed, no GitHub repo was created, gh was not run.

## What works (all run and checked on this box)

- **Brief to variants.** `lpl generate` parses and validates a YAML brief and makes 2 to 5 variants. Each has its own angle, headline, subhead, CTA, hero proof and section order. The offline provider is deterministic (seeded by the brief hash). The LLM provider (Anthropic Messages API shape) is wired and tested with a fake transport only.
- **Copy guard.** Rejects any number not in the brief, hype words, em dashes, over-long copy, bad section orders and duplicate headlines. Runs on offline and LLM output.
- **Static build.** `dist/<variant>/index.html`, a shared CSS file, a router at `dist/index.html`, the `lpl.js` runtime and `manifest.json` with SHA-256 per file.
- **Flag-driven routing.** `lpl.js` asks the PostHog flag for the variant, or uses sticky local hash bucketing when there is no key. It supports `?lpl_variant=` for QA and tags events with `$feature/<flag>`. Tested in Node.
- **Preview.** LocalPreview serves on 127.0.0.1 (tested over HTTP). Vercel and Cloudflare Pages adapters build the full request sequence in dry run, with preview-only guards.
- **PostHog.** Draft experiment, flag rollout PATCH, launch and HogQL count requests use the documented endpoint shapes. Dry run is the default. Live mode needs 5 env guards and a declared sandbox project.
- **Readout.** Bayesian beta-binomial (P(best) and expected loss by exact grid integration), a group-sequential two-proportion z-test (Lan-DeMets O'Brien-Fleming boundaries by recursive numerical integration, matching published values), a Bonferroni split, a chi-square SRM check against the flag's real 34/33/33 split, minimum-sample gates, and a decision of winner, keep running, no winner (keep control) or invalid.
- **Simulation and calibration.** Traffic with known true rates, weekday patterns and optional broken splits. `lpl calibrate` runs 5 scenarios x 300 seeds.
- **Demo.** `lpl demo --docs docs` (`make demo`) runs brief -> 3 variants -> build -> PostHog dry-run plan -> 21 simulated days -> readout.md/json -> docs/hero.png plus variant screenshots. It takes about 4 seconds.
- **Python API.** `create_experiment(...)` and `readout(...)` for channel-loop.

## Tests

- Command: `.venv/bin/pytest -q`
- Result: **116 passed, 0 failed, 0 skipped** (about 12s). This includes the Node runtime tests and the many-seed simulation tests marked slow.
- Lint: `ruff check src tests` passes.
- CI: `.github/workflows/ci.yml` runs ruff, pytest and `lpl demo --no-images` on Python 3.12 and 3.13. It uses no secrets.

## Demo and calibration numbers (SIMULATED)

- Demo, seed 42, true rates a 4.0% / b 4.2% / c 4.8%: keep running on day 7 and day 14, then winner c on day 21. Measured lift +15.4% (95% interval +3.0% to +29.8%), P(best) 97.6%, z 2.45 against a boundary of 2.26.
- Calibration, 300 seeds each: A/A/A false winners 2.3% (naive daily peeking: 40.3%). +20% effect found 77.0% of the time with 0% wrong winners. +10% effect: 78.0% no winner, 0% wrong. Broken split caught 100%.

## Scrub results

- `gitleaks dir . --no-banner --redact`: no leaks found
- `gitleaks git . --no-banner --redact`: no leaks found (7 commits before this receipt)
- `DRY=1 bash publish-private.sh . "x"`: both gitleaks scans clean, scrub grep "clean"
- An extra grep of tracked files for local paths and emails found nothing. The repo has no client names, no real IDs or keys, and no em dashes. `.env.example` holds placeholder names only.

## Simulated, fixture or not executed

- All traffic, conversions and result numbers are SIMULATED. The "Fieldnote" brief and its proof figures and quote are fictional.
- PostHog REST calls: dry-run only. They were never sent to a live project, so the payload shapes are unverified against a real instance.
- Vercel and Cloudflare Pages deploys: dry-run only, never executed. The Cloudflare adapter uses a SHA-256 asset hash, while wrangler uses BLAKE3, so a live run needs a BLAKE3 hash function.
- LLM variant provider: never called. It is tested with a fake transport.

## Notes

- `make` is not installed on this box, so I ran the `make demo` target's command directly (`lpl demo --brief examples/brief.yaml --out out/demo --docs docs`).
- Clean-venv quickstart: the first attempt took 28 min of wall time but only 11s of CPU. That was a pip network stall in the sandbox. A repeat run took 5s.

## Paid-spend ask

None needed. Optional next steps, only with Will's yes:
- Check the PostHog payloads against a free PostHog sandbox project. Cost: $0 on PostHog's free tier.
- One real LLM variant run. Cost: under $0.05 per brief at current Sonnet pricing (about 3K input and 1.5K output tokens).

## Commit

Code and docs HEAD before this receipt: 726e41aabf936563e25116c1698b25f58a1b1991
The final HEAD, including this receipt, is the commit that adds BUILD-RECEIPT.md (`git rev-parse HEAD`).
