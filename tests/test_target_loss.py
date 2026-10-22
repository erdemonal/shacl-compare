import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main

FIX = Path(__file__).parent / "fixtures" / "target_loss"


def test_clear_with_target_loss_not_satisfied(tmp_path: Path):
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
            "http://example.org/ns#Node1",
            "--path",
            "http://example.org/ns#firstName",
            "--source-shape",
            "http://example.org/ns#PersonShape-firstName",
            "--component",
            str(SH.MaxCountConstraintComponent),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["target_membership"] == "LOST"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "NOT_EVALUATED"
    )
    assert (
        "whether_A_clearance_reflects_constraint_satisfaction_or_target_loss"
        in report["undetermined"]
    )
