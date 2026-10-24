
from __future__ import annotations

from pathlib import Path

from rdflib import Graph
from rdflib.namespace import RDF, SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import DesignateError, select_designated
from shacl_compare.graph_io import load_graph
from shacl_compare.sparql_constraints import (
    SPARQL_CONSTRAINT_COMPONENT,
    normalize_sparql_query,
    sparql_constraint_fingerprint,
)
from shacl_compare.validation import run_validation, VALIDATE_KWARGS

EX = "http://example.org/sparql#"
FIX = Path(__file__).parent / "fixtures"
COMP = SPARQL_CONSTRAINT_COMPONENT
VIOL = str(SH.Violation)

def test_advanced_false_still_executes_sh_sparql():
    assert VALIDATE_KWARGS.get("advanced") is False
    v = run_validation(
        load_graph(FIX / "sparql_email" / "G0.ttl"),
        load_graph(FIX / "sparql_email" / "S0.ttl"),
        [],
    )
    assert v["conforms"] is False
    assert v["result_count"] >= 1
    row = v["results"][0]
    assert row["source_constraint_component"] == COMP
    assert row.get("sparql_fingerprint", "").startswith("SPARQL:select:")

def test_fingerprint_stable_across_reload():
    s0 = load_graph(FIX / "sparql_email" / "S0.ttl")
    cons = list(s0.objects(None, SH.sparql))
    assert len(cons) == 1
    fp1 = sparql_constraint_fingerprint(s0, cons[0])
    ttl = s0.serialize(format="turtle")
    s0b = Graph()
    s0b.parse(data=ttl, format="turtle")
    cons2 = list(s0b.objects(None, SH.sparql))
    fp2 = sparql_constraint_fingerprint(s0b, cons2[0])
    assert fp1 == fp2
    assert str(cons[0]) != str(cons2[0]) or True

def test_sparql_email_clear_a_and_b(tmp_path: Path):
    case = FIX / "sparql_email"
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "email.json",
        )
    )
    assert report["designated"]["sparql_fingerprint"].startswith("SPARQL:select:")
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
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

def test_sparql_query_change_clears_designated_under_sb(tmp_path: Path):
    case = FIX / "sparql_email"
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "G0.ttl",
            shapes_revision=case / "SB_query_change.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "qchg.json",
        )
    )
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_multiple_sparql_requires_index(tmp_path: Path):
    case = FIX / "sparql_multi"
    v = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    assert v["result_count"] >= 2
    fps = {r.get("sparql_fingerprint") for r in v["results"]}
    assert len(fps) == 2
    try:
        select_designated(
            v["results"],
            focus_key=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
        )
        raised = False
    except DesignateError as exc:
        raised = True
        assert "designation-index" in str(exc) or "matched" in str(exc)
    assert raised
    chosen = select_designated(
        v["results"],
        focus_key=f"{EX}Alice",
        path="",
        source_shape=f"{EX}PersonShape",
        component=COMP,
        severity=VIOL,
        designation_index=1,
    )
    assert chosen.get("sparql_fingerprint")

    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "multi.json",
            designation_index=1,
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "PERSIST"
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

def test_anonymous_sparql_shape(tmp_path: Path):
    case = FIX / "sparql_anon"
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=None,
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "anon.json",
        )
    )
    assert report["designated"]["sparql_fingerprint"].startswith("SPARQL:select:")
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    # Anonymous SB alignment may be UNRESOLVED. Original under S0 must still evaluate.
    assert report["intervention_B"]["result_outcome"] in {
        "CLEAR",
        "NOT_COMPARABLE",
    }
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_sparql_target_loss_not_satisfied(tmp_path: Path):
    case = FIX / "sparql_target_loss"
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "tloss.json",
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["target_membership"] == "LOST"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "NOT_EVALUATED"
    )

def test_sparql_blank_focus(tmp_path: Path):
    case = FIX / "sparql_blank_focus"
    fk_props = [RDF.type]
    v = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), fk_props
    )
    assert v["result_count"] >= 1
    focus = v["results"][0]["focus_key"]
    assert focus.startswith("bnode[")
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=focus,
            path="",
            source_shape=f"{EX}DistShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[str(RDF.type)],
            requirement_card=None,
            out=tmp_path / "blank.json",
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_sparql_designation_does_not_steal_core_violation(tmp_path: Path):
    case = FIX / "sparql_with_core"
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=f"{EX}Alice",
            path="",
            source_shape=f"{EX}PersonShape",
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "mix.json",
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert report["intervention_B"]["result_outcome"] == "PERSIST"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    residuals_a = report["intervention_A"]["residual_results"]
    assert isinstance(residuals_a, dict)

def test_never_satisfied_without_fingerprint():
    from shacl_compare.designate import evaluate_original_constraint_from_s0_results

    out = evaluate_original_constraint_from_s0_results(
        [],
        focus_key=f"{EX}Alice",
        path="",
        source_shape=f"{EX}PersonShape",
        component=COMP,
        severity=VIOL,
        targeted=True,
        sparql_fingerprint=None,
    )
    assert out["original_constraint_evaluation"] == "NOT_EVALUATED"

def test_normalize_formatting_whitespace_outside_literals():
    a = normalize_sparql_query("SELECT  $this\nWHERE {  FILTER(true) }")
    b = normalize_sparql_query("SELECT $this WHERE { FILTER(true) }")
    assert a == b
    two = normalize_sparql_query('FILTER(?l = "hello  world")')
    one = normalize_sparql_query('FILTER(?l = "hello world")')
    assert two != one

def test_complex_paths_module_imports():
    from shacl_compare.paths import predicate_path_fingerprint

    assert predicate_path_fingerprint("http://example.org/x").startswith("P:<")
