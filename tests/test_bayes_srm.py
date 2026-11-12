import pytest

from landing_page_lab.stats import ArmCounts, analyze, monte_carlo, relative_uplift_interval, srm_check

ARMS = [ArmCounts("a", 10_000, 400), ArmCounts("b", 10_000, 430), ArmCounts("c", 10_000, 470)]


def test_grid_matches_monte_carlo():
    r = analyze(ARMS, control="a")
    pb, loss = monte_carlo(ARMS, draws=60_000, seed=3)
    for arm, p, lo in zip(r.arms, pb, loss):
        assert arm.prob_best == pytest.approx(p, abs=0.006)
        assert arm.expected_loss == pytest.approx(lo, abs=0.0002)


def test_prob_best_sums_to_one_and_identical_arms_split_evenly():
    r = analyze([ArmCounts(n, 5000, 200) for n in "abcd"])
    assert sum(a.prob_best for a in r.arms) == pytest.approx(1.0)
    for a in r.arms:
        assert a.prob_best == pytest.approx(0.25, abs=0.01)


def test_leader_and_pairwise():
    r = analyze(ARMS, control="a")
    assert r.leader.name == "c"
    assert r.by_name("a").prob_beats_control is None
    assert r.by_name("c").prob_beats_control > 0.98
    assert r.by_name("c").expected_loss < r.by_name("a").expected_loss


def test_credible_interval_brackets_mean():
    for a in analyze(ARMS).arms:
        assert a.ci_low < a.mean < a.ci_high


def test_zero_and_tiny_counts_do_not_crash():
    r = analyze([ArmCounts("a", 0, 0), ArmCounts("b", 3, 0), ArmCounts("c", 3, 3)])
    assert sum(a.prob_best for a in r.arms) == pytest.approx(1.0)
    assert r.leader.name == "c"


def test_uplift_interval():
    mid, lo, hi = relative_uplift_interval(ARMS[2], ARMS[0], draws=20_000, seed=1)
    assert lo < 0.175 < hi and lo < mid < hi


def test_bad_inputs():
    with pytest.raises(ValueError):
        ArmCounts("x", 10, 11)
    with pytest.raises(ValueError):
        analyze([ARMS[0]])
    with pytest.raises(KeyError):
        analyze(ARMS, control="zzz")


def test_srm_ok_and_mismatch():
    ok = srm_check([ArmCounts("a", 10_050, 1), ArmCounts("b", 9_950, 1)], [1, 1])
    assert not ok.mismatch and ok.p_value > 0.3
    bad = srm_check([ArmCounts("a", 10_600, 1), ArmCounts("b", 9_400, 1)], [1, 1])
    assert bad.mismatch and bad.p_value < 1e-10


def test_srm_uses_planned_weights():
    counts = [ArmCounts("a", 13_600, 1), ArmCounts("b", 13_200, 1), ArmCounts("c", 13_200, 1)]
    assert srm_check(counts, [34, 33, 33]).p_value > 0.9
    assert srm_check(counts, [1, 1, 1]).p_value < 0.05  # assuming "equal" would raise a false alarm


def test_srm_validates():
    with pytest.raises(ValueError):
        srm_check([ArmCounts("a", 1, 0)], [1, 1])
    with pytest.raises(ValueError):
        srm_check([ArmCounts("a", 1, 0), ArmCounts("b", 1, 0)], [1, 0])
