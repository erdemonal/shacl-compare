import json
from pathlib import Path

from rdflib import URIRef
from rdflib.namespace import SH

from shacl_compare.cli import main
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

FIX = Path(__file__).parent / "fixtures" / "bnode_data"


def test_bnode_data_diff_ambiguous_but_validation_runs(tmp_path: Path):
    props = [URIRef("http://example.org/ns#label")]
    base = run_validation(
        load_graph(FIX / "G0.ttl"),
        load_graph(FIX / "S0.ttl"),
        props,
    )
    assert base["result_count"] >= 1
    focus_key = base["results"][0]["focus_key"]

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
            focus_key,
            "--path",
            "http://example.org/ns#label",
            "--source-shape",
            "http://example.org/ns#ItemShape-label",
            "--component",
            str(SH.MaxCountConstraintComponent),
            "--focus-key",
            "http://example.org/ns#label",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["data_diff"]["diff_status"] == "AMBIGUOUS"
    assert report["data_diff"]["deletion_count"] is None
    assert report["data_diff"]["rdf_triple_deletions"] == []
    assert "exact_data_triple_edit_list" in report["undetermined"]
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
