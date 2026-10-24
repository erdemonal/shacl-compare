import json
import subprocess
import sys
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main
from shacl_compare.designate import DesignateError, select_designated
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

FIX = Path(__file__).parent / "fixtures" / "anonymous_maxcount"
AMBIG = Path(__file__).parent / "fixtures" / "anonymous_ambiguous"
COMP = str(SH.MaxCountConstraintComponent)

def test_select_without_source_shape_for_anonymous_ps():
    baseline = run_validation(load_graph(FIX / "G0.ttl"), load_graph(FIX / "S0.ttl"), [])
    assert baseline["result_count"] == 1
    row = select_designated(
        baseline["results"],
        focus_key="http://example.org/anon#Item1",
        path="http://example.org/anon#code",
        component=COMP,
        severity=str(SH.Violation),
        source_shape=None,
    )
    assert row["_designation_mode"] == "core_signature"
    assert row["source_shape"]
    assert not str(row["source_shape"]).startswith("http")

def test_stale_blank_id_ignored_when_not_absolute_iri():
    baseline = run_validation(load_graph(FIX / "G0.ttl"), load_graph(FIX / "S0.ttl"), [])
    row = select_designated(
        baseline["results"],
        focus_key="http://example.org/anon#Item1",
        path="http://example.org/anon#code",
        component=COMP,
        severity=str(SH.Violation),
        source_shape="n00staleblankid",
    )
    assert row["_designation_mode"] == "core_signature"

def test_anonymous_compare_cli(tmp_path: Path):
    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(FIX / "G0.ttl"),
            "--shapes-baseline",
            str(FIX / "S0.ttl"),
            "--data-repair",
            str(FIX / "GA.ttl"),
            "--shapes-revision",
            str(FIX / "SB.ttl"),
            "--focus",
            "http://example.org/anon#Item1",
            "--path",
            "http://example.org/anon#code",
            "--component",
            COMP,
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["designated"]["designation_mode"] == "core_signature"
    assert report["designated"]["source_shape_is_absolute_iri"] is False
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["target_membership"] == "RETAINED"
    assert report["intervention_B"]["target_membership"] == "RETAINED"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_anonymous_cli_separate_process(tmp_path: Path):
    import os

    out = tmp_path / "report.json"
    src_root = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    cmd = [
        sys.executable,
        "-m",
        "shacl_compare.cli",
        "--data-baseline",
        str(FIX / "G0.ttl"),
        "--shapes-baseline",
        str(FIX / "S0.ttl"),
        "--data-repair",
        str(FIX / "GA.ttl"),
        "--shapes-revision",
        str(FIX / "SB.ttl"),
        "--focus",
        "http://example.org/anon#Item1",
        "--path",
        "http://example.org/anon#code",
        "--component",
        COMP,
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text())
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"

def test_ambiguous_requires_designation_index():
    baseline = run_validation(
        load_graph(AMBIG / "G0.ttl"), load_graph(AMBIG / "S0.ttl"), []
    )
    assert baseline["result_count"] >= 2
    try:
        select_designated(
            baseline["results"],
            focus_key="http://example.org/ambig#N",
            path="http://example.org/ambig#p",
            component=COMP,
            severity=str(SH.Violation),
            source_shape=None,
        )
        raise AssertionError("expected DesignateError")
    except DesignateError as exc:
        assert "designation-index" in str(exc)

    row = select_designated(
        baseline["results"],
        focus_key="http://example.org/ambig#N",
        path="http://example.org/ambig#p",
        component=COMP,
        severity=str(SH.Violation),
        source_shape=None,
        designation_index=1,
    )
    assert "with_index" in row["_designation_mode"]

def test_iri_source_shape_still_required_match_when_provided():
    baseline = run_validation(
        load_graph(
            Path(__file__).parent / "fixtures" / "maxcount" / "G0.ttl"
        ),
        load_graph(
            Path(__file__).parent / "fixtures" / "maxcount" / "S0.ttl"
        ),
        [],
    )
    try:
        select_designated(
            baseline["results"],
            focus_key="http://example.org/ns#InvalidPerson",
            path="http://example.org/ns#firstName",
            component=COMP,
            severity=str(SH.Violation),
            source_shape="http://example.org/ns#WrongShape",
        )
        raise AssertionError("expected DesignateError")
    except DesignateError as exc:
        assert "matched 0" in str(exc)
