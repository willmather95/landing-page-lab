# Readout: fieldnote-hero-test (SIMULATED)

**Winner: c (+15.4% vs a, P(best) 97.6%)**

Day 21, look 3 of 3. Status: `winner`.

| Variant | Visitors | Conversions | Rate | 95% credible | P(best) | Exp. loss | Lift vs control | z | p |
|---|---:|---:|---:|---|---:|---:|---|---:|---:|
| a | 13,195 | 524 | 3.97% | 3.65% to 4.32% | 0.6% | 0.615 pts | control |  |  |
| b | 13,027 | 528 | 4.05% | 3.73% to 4.41% | 1.7% | 0.533 pts | +2.1% (-9.2% to +15.0%) | 0.34 | 0.7354 |
| c | 12,915 | 592 | 4.58% | 4.24% to 4.96% | 97.6% | 0.002 pts | +15.4% (+3.0% to +29.8%) | 2.45 | 0.0144 |

## Gates

- PASS **Sample ratio**: p = 0.386 (stop if < 0.001)
- PASS **Minimum sample**: all arms above minimum
- PASS **Bayesian**: c: P(best) 97.6% (need 95%), expected loss 0.002 pts (cap 0.040)
- PASS **Sequential z-test**: c vs a: z 2.45, need >= 2.26

## Data quality

- Sample ratio check: observed 13,195, 13,027, 12,915 vs expected 13,307, 12,915, 12,915; chi-square 1.90, p = 0.386 (ok, threshold 0.001).

## How this was decided

- Planned looks only (day 7: |z| >= 4.17, day 14: |z| >= 2.85, day 21: |z| >= 2.26). Lan-DeMets obrien-fleming alpha spending, total alpha 0.05, split across 2 challenger comparisons.
- Bayesian gate: Beta(1, 1) prior, P(best) >= 95% and expected loss <= 1% of the control rate.
- Minimum per arm: 1,000 visitors and 30 conversions.
- A daily fixed-horizon p-value is shown for context only. Acting on it at every peek inflates false winners.

## Every planned look

| Day | Status | Leader | P(best) | Boundary |z| |
|---:|---|---|---:|---:|
| 7 | `keep_running` | c | 64.9% | 4.17 |
| 14 | `keep_running` | c | 81.5% | 2.85 |
| 21 | `winner` | c | 97.6% | 2.26 |

Simulation: true rates a 4.0%, b 4.2%, c 4.8%; 2,000 visitors a day before weekday swings; seed 42. These are made-up visitors, not real traffic.
