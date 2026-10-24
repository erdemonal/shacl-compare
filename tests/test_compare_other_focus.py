import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main

FIX = Path(__file__).parent / "fixtures" / "other_focus"

def test_other_focus_differential(tmp_path: Path):
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
            "http://example.org/ns#PersonA",
            "--path",
            "http://example.org/ns#firstName",
            "--source-shape",
            "http://example.org/ns#PersonShape-firstName",
            "--component",
            str(SH.MinCountConstraintComponent),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["conforms"] is False
    assert report["intervention_B"]["conforms"] is True
    other_a = {
        r["focus_key"]: r["result_outcome"]
        for r in report["intervention_A"]["other_focus_nodes"]
    }
    other_b = {
        r["focus_key"]: r["result_outcome"]
        for r in report["intervention_B"]["other_focus_nodes"]
    }
    assert other_a["http://example.org/ns#PersonB"] == "PERSIST"
    assert other_b["http://example.org/ns#PersonB"] == "CLEAR"
