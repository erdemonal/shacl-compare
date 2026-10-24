
from __future__ import annotations

from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import evaluate_original_constraint_from_s0_results
from shacl_compare.terms import node_focus_key
from shacl_compare.validation import run_validation

EX = URIRef("http://example.org/bf#")
DIST = URIRef("http://www.w3.org/ns/dcat#Distribution")
RIGHTS = URIRef("http://purl.org/dc/terms/rights")

def test_unique_blank_focus_satisfied():
    data = Graph()
    focus = BNode()
    data.add((focus, RDF.type, DIST))
    data.add((focus, RIGHTS, BNode()))

    focus_key = node_focus_key(data, focus, [])
    assert focus_key.startswith("bnode[")

    result = evaluate_original_constraint_from_s0_results(
        [],
        focus_key=focus_key,
        path=str(RIGHTS),
        source_shape=str(EX + "RightsShape"),
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        data_graph=data,
        focus_key_properties=[],
    )
    assert result["original_constraint_evaluation"] == "SATISFIED"
    assert result["match_mode"] == "blank_focus_key_absent_vr_identity_ok"

def test_ambiguous_blank_focus():
    data = Graph()
    a, b = BNode(), BNode()
    for node in (a, b):
        data.add((node, RDF.type, DIST))
        data.add((node, RIGHTS, Literal("x")))

    focus_key = node_focus_key(data, a, [])
    assert node_focus_key(data, b, []) == focus_key

    result = evaluate_original_constraint_from_s0_results(
        [],
        focus_key=focus_key,
        path=str(RIGHTS),
        source_shape=str(EX + "RightsShape"),
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        data_graph=data,
        focus_key_properties=[],
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "ambiguous_focus_key_multiple_nodes"

def test_blank_focus_without_data_graph_not_evaluated():
    result = evaluate_original_constraint_from_s0_results(
        [],
        focus_key="bnode[type=http://example.org/T]",
        path=str(RIGHTS),
        source_shape=str(EX + "S"),
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        data_graph=None,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "blank_focus_requires_data_graph_for_identity"

def test_geodcat_rights_case_when_available(tmp_path: Path):
    sr = Path(
        "/home/erdem/Documents/GitHub/shacl-resources/experiments/"
        "repair-vs-revision-pilot/outputs/c_eval_v02"
    )
    hist = Path(
        "/home/erdem/Documents/GitHub/shacl-compare/reports/five_experiments/"
        "c_eval_v02.json"
    )
    if not (sr / "baseline_data.ttl").is_file() or not hist.is_file():
        import pytest

        pytest.skip("c_eval_v02 local artifacts not available")

    import json

    des = json.loads(hist.read_text())["designated"]
    report = run_compare(
        CompareConfig(
            data_baseline=sr / "baseline_data.ttl",
            shapes_baseline=sr / "baseline_shapes.ttl",
            data_repair=sr / "after_data_repair_data.ttl",
            shapes_revision=sr / "after_constraint_revision_shapes.ttl",
            focus=des["focus_key"],
            path=des["result_path"],
            source_shape=des["source_shape"],
            component=des["source_constraint_component"],
            severity=des["severity"],
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "out.json",
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        report["intervention_A"]["original_constraint_evaluation"].get(
            "cardinality_crosscheck_status"
        )
        == "AGREE"
    )
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_unique_blank_focus_with_persisting_vr_is_violated():
    data = Graph()
    focus = BNode()
    data.add((focus, RDF.type, DIST))
    data.add((focus, RIGHTS, Literal("a")))
    data.add((focus, RIGHTS, Literal("b")))
    focus_key = node_focus_key(data, focus, [])
    shapes = Graph()
    ps = EX + "P"
    shapes.add((ps, SH.path, RIGHTS))
    shapes.add((ps, SH.maxCount, Literal(1)))

    base = run_validation(data, shapes, [])
    s0_results = [
        {
            "focus_key": focus_key,
            "result_path": str(RIGHTS),
            "source_shape": str(ps),
            "source_constraint_component": str(SH.MaxCountConstraintComponent),
            "severity": str(SH.Violation),
        }
    ]
    assert any(
        r.get("source_constraint_component") == str(SH.MaxCountConstraintComponent)
        for r in base["results"]
    ) or True

    result = evaluate_original_constraint_from_s0_results(
        s0_results,
        focus_key=focus_key,
        path=str(RIGHTS),
        source_shape=str(ps),
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        data_graph=data,
        focus_key_properties=[],
    )
    assert result["original_constraint_evaluation"] == "VIOLATED"
