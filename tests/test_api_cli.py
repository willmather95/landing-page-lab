import json

import pytest

from landing_page_lab import Status, create_experiment, plan_traffic, readout
from landing_page_lab.cli import main


def test_plan_rounds_to_whole_weeks(brief):
    p = plan_traffic(brief)
    assert p.visitors_per_arm > 10_000 and p.days_needed == 19
    assert p.look_days == (7, 14, 21)


def test_create_experiment_end_to_end(brief_path, tmp_path):
    h = create_experiment(brief_path, out_dir=tmp_path)
    assert h.dry_run and h.control == "a" and h.weights == (34.0, 33.0, 33.0)
    assert (tmp_path / "dist" / "c" / "index.html").exists()
    summary = json.loads((tmp_path / "experiment.json").read_text())
    assert summary["posthog"]["flag_key"] == "fieldnote-hero-test"
    reqs = json.loads((tmp_path / "posthog-requests.json").read_text())
    assert [r["method"] for r in reqs] == ["GET", "POST", "PATCH"]


def test_readout_with_handle_uses_the_flag_split(brief_path, tmp_path):
    h = create_experiment(brief_path, out_dir=tmp_path)
    # A 34/33/33 split that would trip SRM if the readout assumed equal weights.
    counts = {"a": (13_600, 545), "b": (13_200, 530), "c": (13_200, 690)}
    r = readout(counts, day=21, handle=h)
    assert not r.srm.mismatch and r.status is Status.WINNER and r.winner == "c"
    assert readout(counts, day=21).srm.p_value < r.srm.p_value


def test_create_experiment_needs_out_dir_to_build(brief):
    with pytest.raises(ValueError):
        create_experiment(brief)


def test_cli_generate_and_plan(brief_path, tmp_path, capsys):
    assert main(["generate", str(brief_path), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 3
    assert main(["plan", str(brief_path), "--out", str(tmp_path / "plan")]) == 0
    assert "feature_flag_variants" in capsys.readouterr().out


def test_cli_simulate_then_readout(tmp_path, capsys):
    csv = tmp_path / "t.csv"
    assert main(["simulate", "--rates", "a=0.03,b=0.06", "--seed", "3", "--out", str(csv)]) == 0
    capsys.readouterr()
    assert main(["readout", "--csv", str(csv), "--day", "14", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["status"] == "winner" and d["winner"] == "b"


def test_cli_readout_counts(capsys):
    assert main(["readout", "--counts", "a=13000/520,b=13000/680", "--day", "10"]) == 0
    assert "Keep running" in capsys.readouterr().out


def test_cli_build_and_deploy_dry_run(brief_path, tmp_path, capsys):
    out = tmp_path / "dist"
    assert main(["build", str(brief_path), "--out", str(out)]) == 0
    assert main(["deploy", str(out), "--adapter", "vercel", "--project", "lpl-demo"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out


def test_cli_demo_without_images(brief_path, tmp_path, capsys):
    assert main(["demo", "--brief", str(brief_path), "--out", str(tmp_path / "demo"), "--no-images"]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "readout:" in out
    md = (tmp_path / "demo" / "readout.md").read_text()
    assert "Every planned look" in md and "SIMULATED" in md
    assert (tmp_path / "demo" / "hero.html").exists()
