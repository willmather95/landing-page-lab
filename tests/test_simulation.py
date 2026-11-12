"""The readout must recover known truths at the expected rates. Every row here is SIMULATED."""

import pytest

from landing_page_lab.calibrate import SCENARIOS, run_scenario
from landing_page_lab.simulate import (TrueArm, cumulative, from_csv, naive_peeking_false_call, run_sequential,
                                       simulate_traffic, to_csv)

SEEDS = range(5000, 5150)  # 150 seeds per scenario; a different range from the published calibration


def test_traffic_is_reproducible_and_roughly_right():
    arms = [TrueArm("a", 0.04), TrueArm("b", 0.05)]
    rows = simulate_traffic(arms, days=21, daily_visitors=2000, seed=9)
    assert rows == simulate_traffic(arms, days=21, daily_visitors=2000, seed=9)
    cum = cumulative(rows, 21, ["a", "b"])
    total = sum(a.visitors for a in cum)
    assert 0.85 * 42_000 < total < 1.0 * 42_000          # weekend dip lowers the average day
    assert abs(cum[0].visitors - cum[1].visitors) < 0.03 * total
    assert 0.033 < cum[0].rate < 0.043 and 0.042 < cum[1].rate < 0.054


def test_csv_roundtrip():
    rows = simulate_traffic([TrueArm("a", 0.04), TrueArm("b", 0.04)], days=3, seed=1)
    assert from_csv(to_csv(rows)) == rows


def test_actual_weights_inject_a_broken_split():
    rows = simulate_traffic([TrueArm("a", 0.04), TrueArm("b", 0.04)], days=14, seed=2, actual_weights=[0.6, 0.4])
    a, b = cumulative(rows, 14, ["a", "b"])
    assert a.visitors / (a.visitors + b.visitors) == pytest.approx(0.6, abs=0.02)


@pytest.mark.slow
def test_aa_false_winner_rate_stays_under_alpha():
    r = run_scenario(SCENARIOS[0], SEEDS, with_naive=True)
    assert r.wrong_winner <= 0.05
    # The reason the policy exists: peeking daily at p < 0.05 calls far more false winners.
    assert r.naive_peeking_calls >= 0.20
    assert r.naive_peeking_calls > 5 * max(r.wrong_winner, 0.01)


@pytest.mark.slow
def test_recovers_true_winner_with_planned_power():
    r = run_scenario(SCENARIOS[1], SEEDS)            # c is +20%, planned for 80% power
    assert r.right_winner >= 0.65
    assert r.wrong_winner <= 0.01


@pytest.mark.slow
def test_underpowered_effect_mostly_keeps_control_and_never_flips():
    r = run_scenario(SCENARIOS[3], SEEDS)            # c is +10%, half the planned effect
    assert r.no_winner >= 0.6
    assert r.wrong_winner <= 0.01


@pytest.mark.slow
def test_broken_split_is_caught():
    r = run_scenario(SCENARIOS[4], range(5000, 5060))
    assert r.srm_stops >= 0.95
    assert r.right_winner + r.wrong_winner == 0


def test_run_sequential_stops_at_first_call():
    arms = [TrueArm("a", 0.03), TrueArm("b", 0.06)]
    run = run_sequential(arms, seed=4)
    assert run.winner == "b"
    assert run.decision_day == run.history[-1].day
    assert all(h.winner is None for h in run.history[:-1])


def test_naive_peeking_helper_flags_obvious_difference():
    rows = simulate_traffic([TrueArm("a", 0.02), TrueArm("b", 0.08)], days=3, seed=1)
    assert naive_peeking_false_call(rows, ["a", "b"])
