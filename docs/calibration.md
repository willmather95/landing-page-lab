# Calibration (SIMULATED)

300 seeds per scenario, 2,000 visitors a day before weekday swings, 3 arms split 34/33/33, looks on days 7, 14, 21.
Default policy: P(best) >= 95%, expected loss <= 1% of control, O'Brien-Fleming boundaries, alpha 0.05 split over 2 comparisons.

| Scenario | Right winner | Wrong winner | No winner | SRM stop | Mean call day |
|---|---:|---:|---:|---:|---:|
| A/A/A: all 4.0% | 0.0% | 2.3% | 97.7% | 0.0% | 20.0 |
| c is +20% | 77.0% | 0.0% | 23.0% | 0.0% | 17.2 |
| demo truth: b +5%, c +20% | 67.3% | 0.0% | 32.7% | 0.0% | 17.2 |
| c is +10% (underpowered) | 22.0% | 0.0% | 78.0% | 0.0% | 18.7 |
| broken split 37/32/31 | 0.0% | 0.0% | 0.0% | 100.0% |  |

Same A/A/A traffic, read the naive way (stop the first day any p < 0.05): **40.3%** of runs call a false winner, vs **2.3%** with this readout.

Runtime: 24s. Reproduce: `lpl calibrate --seeds 300`.
