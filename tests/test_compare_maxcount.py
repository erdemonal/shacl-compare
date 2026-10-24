import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main

FIX = Path(__file__).parent / "fixtures" / "maxcount"

def test_maxcount_compare(tmp_path: Path):
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
            "http://example.org/ns#InvalidPerson",
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
    assert report["baseline"]["conforms"] is False
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
    assert report["data_diff"]["diff_status"] == "RESOLVED"
    assert report["data_diff"]["deletion_count"] == 1
    assert report["shapes_diff"]["diff_status"] == "RESOLVED"
    assert report["comparison"]["ranking"] is None
    assert report["meta"]["interface"]["A_validates_with"] == "S0"
