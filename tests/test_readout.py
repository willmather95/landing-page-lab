import json

import pytest

from landing_page_lab.readout import Policy, Status, readout
from landing_page_lab.stats import ArmCounts

STRONG = {"a": (13_000, 520), "b": (13_000, 530), "c": (13_000, 680)}


def test_winner_at_a_planned_look():
    r = readout(STRONG, day=21)
    assert r.status is Status.WINNER and r.winner == "c"
    assert all(g.passed for g in r.gates)
    assert r.decided and r.next_look_day is None


def test_same_counts_between_looks_never_decide():
    r = readout(STRONG, day=10)
    assert r.status is Status.KEEP_RUNNING and r.winner is None
    assert r.look is None and r.next_look_day == 14
    assert any("between planned looks" in n for n in r.notes)


def test_no_day_means_report_only():
    r = readout(STRONG, day=None)
    assert r.status is Status.KEEP_RUNNING


def test_early_look_needs_a_much_bigger_z():
    # z about 2.9: enough at the final look, not at day 7 where the boundary is about 4.2.
    counts = {"a": (13_000, 520), "b": (13_000, 520), "c": (13_000, 610)}
    assert readout(counts, day=21).status is Status.WINNER
    assert readout(counts, day=7).status is Status.KEEP_RUNNING


def test_final_look_without_winner_keeps_control():
    r = readout({"a": (13_000, 520), "b": (13_000, 525), "c": (13_000, 540)}, day=21)
    assert r.status is Status.NO_WINNER
    assert "Keep a" in r.headline()


def test_after_final_look_counts_as_final():
    r = readout({"a": (13_000, 520), "b": (13_000, 525), "c": (13_000, 540)}, day=30)
    assert r.status is Status.NO_WINNER


def test_control_can_win():
    r = readout({"a": (13_000, 700), "b": (13_000, 520), "c": (13_000, 530)}, day=21)
    assert r.status is Status.WINNER and r.winner == "a"
    assert "control beats every challenger" in r.headline()


def test_minimum_sample_gate():
    r = readout({"a": (900, 20), "b": (900, 60)}, day=21, policy=Policy(min_visitors_per_arm=1000))
    gate = next(g for g in r.gates if g.name == "Minimum sample")
    assert not gate.passed and r.status is Status.NO_WINNER


def test_srm_overrides_everything():
    r = readout({"a": (14_000, 520), "b": (12_000, 530), "c": (13_000, 680)}, day=21)
    assert r.status is Status.INVALID_SRM and r.winner is None
    assert "sample ratio mismatch" in r.headline()


def test_bayesian_gate_can_block_a_significant_z():
    # Two strong challengers split P(best), so the Bayesian gate holds even though c beats control.
    r = readout({"a": (13_000, 520), "b": (13_000, 670), "c": (13_000, 680)}, day=21)
    assert r.status is not Status.WINNER
    assert not next(g for g in r.gates if g.name == "Bayesian").passed


def test_accepts_armcounts_and_custom_control():
    arms = [ArmCounts("x", 13_000, 680), ArmCounts("ctrl", 13_000, 520)]
    r = readout(arms, control="ctrl", day=21)
    assert r.control == "ctrl" and r.winner == "x"


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        readout({"a": (10, 1)}, day=21)
    with pytest.raises(KeyError):
        readout(STRONG, control="nope", day=21)
    with pytest.raises(ValueError):
        readout([ArmCounts("a", 10, 1), ArmCounts("a", 10, 1)], day=21)
    with pytest.raises(ValueError):
        Policy(look_days=(14, 7))


def test_markdown_and_json():
    r = readout(STRONG, day=21)
    md = r.to_markdown()
    assert "Winner: c" in md and "| c |" in md and "Sample ratio check" in md and "\u2014" not in md
    d = json.loads(r.to_json())
    assert d["status"] == "winner" and d["winner"] == "c" and len(d["arms"]) == 3
