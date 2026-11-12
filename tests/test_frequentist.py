import math
import random

import pytest

from landing_page_lab.stats import ArmCounts, boundaries, required_sample_per_arm, spent_alpha, two_proportion_ztest


def test_single_look_is_the_usual_1_96():
    assert boundaries([1.0]) == (pytest.approx(1.959964, abs=1e-5),)


def test_obrien_fleming_matches_published_lan_demets_values():
    # Reference: Lan-DeMets O'Brien-Fleming-type spending, two-sided alpha 0.05, equal looks
    # (same values as gsDesign sfLDOF / Jennison & Turnbull tables).
    assert boundaries([1 / 3, 2 / 3, 1]) == pytest.approx((3.7103, 2.5114, 1.9930), abs=2e-3)
    assert boundaries([0.2, 0.4, 0.6, 0.8, 1.0]) == pytest.approx((4.8769, 3.3569, 2.6803, 2.2898, 2.0310), abs=2e-3)


def test_pocock_boundaries_are_nearly_flat_and_above_1_96():
    b = boundaries([1 / 3, 2 / 3, 1], kind="pocock")
    assert all(2.2 < z < 2.4 for z in b)


def test_boundaries_hold_type_one_error_by_monte_carlo():
    rng = random.Random(7)
    fr = [1 / 3, 2 / 3, 1.0]
    bnd = boundaries(fr, 0.05)
    sims, rejects = 40_000, 0
    for _ in range(sims):
        s, prev = 0.0, 0.0
        for t, c in zip(fr, bnd):
            s += rng.gauss(0.0, math.sqrt(t - prev))
            prev = t
            if abs(s / math.sqrt(t)) >= c:
                rejects += 1
                break
    assert rejects / sims == pytest.approx(0.05, abs=0.006)


def test_spending_is_monotone_and_hits_alpha():
    vals = [spent_alpha(t, 0.05) for t in (0.1, 0.3, 0.6, 1.0)]
    assert vals == sorted(vals)
    assert vals[-1] == pytest.approx(0.05)
    assert spent_alpha(0, 0.05) == 0


def test_boundaries_reject_bad_fractions():
    for bad in ([], [0.5, 0.4], [0, 1], [0.5, 1.2]):
        with pytest.raises(ValueError):
            boundaries(bad)


def test_two_proportion_ztest_hand_computed():
    t = two_proportion_ztest(ArmCounts("b", 10_000, 470), ArmCounts("a", 10_000, 400))
    pooled = 870 / 20_000
    z = 0.007 / math.sqrt(pooled * (1 - pooled) * 2 / 10_000)
    assert t.z == pytest.approx(z)
    assert t.relative_lift == pytest.approx(0.175)
    assert t.ci_low < 0.007 < t.ci_high
    assert 0.01 < t.p_value < 0.02


def test_ztest_empty_arm_is_neutral():
    t = two_proportion_ztest(ArmCounts("b", 0, 0), ArmCounts("a", 100, 5))
    assert t.p_value == 1.0 and t.z == 0.0


def test_required_sample_textbook_value():
    # 4% -> 4.8%, alpha 0.05 two-sided, 80% power: about 10.3k per arm (standard formula).
    n = required_sample_per_arm(0.04, 0.20)
    assert 10_200 < n < 10_400
    assert required_sample_per_arm(0.04, 0.20, comparisons=2) > n
    with pytest.raises(ValueError):
        required_sample_per_arm(0.9, 0.5)
