import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main

FIX = Path(__file__).parent / "fixtures" / "maxcount"


def test_requirement_card(tmp_path: Path):
    card = tmp_path / "card.json"
    card.write_text(
        json.dumps(
            {
                "shape": "http://example.org/ns#PersonShape-firstName",
                "path": "http://example.org/ns#firstName",
                "parameter": "sh:maxCount",
                "expected_value": 1,
                "citation": "test-only",
            }
        )
    )
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
            "--requirement-card",
            str(card),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["requirement_card"]["on_baseline_shapes"]["status"] == "CONDITION_HELD"
    assert (
        report["requirement_card"]["on_revision_shapes"]["status"]
        == "CONDITION_DIFFERENT"
    )
