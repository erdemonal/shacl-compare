
from __future__ import annotations

from pathlib import Path

import pytest
from rdflib.namespace import SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import DesignateError, select_designated
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

VIOL = str(SH.Violation)
WARN = str(SH.Warning)
INFO = str(SH.Info)
COMP_MIN = str(SH.MinCountConstraintComponent)
SPARQL = str(SH.SPARQLConstraintComponent)

def _write(tmp: Path, name: str, files: dict[str, str]) -> Path:
    d = tmp / name
    d.mkdir()
    for fname, body in files.items():
        (d / fname).write_text(body.strip() + "\n", encoding="utf-8")
    return d

def _run(
    case: Path,
    *,
    focus: str,
    path: str,
    source_shape: str | None,
    component: str,
    severity: str,
    out: Path,
) -> dict:
    return run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=focus,
            path=path,
            source_shape=source_shape,
            component=component,
            severity=severity,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )

def _severities(case: Path, data: str, shapes: str) -> list[str]:
    v = run_validation(load_graph(case / data), load_graph(case / shapes), [])
    return [str(r.get("severity", "")).rsplit("#", 1)[-1] for r in v["results"]]


def test_default_violation_clear(tmp_path: Path):
    ns = "http://example.org/p3/def#"
    case = _write(
        tmp_path,
        "def",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 .
""",
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:p "x" .',
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 0 .
""",
        },
    )
    assert _severities(case, "G0.ttl", "S0.ttl") == ["Violation"]
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=VIOL,
        out=tmp_path / "def.json",
    )
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

def test_warning_clear_and_info_persist(tmp_path: Path):
    ns = "http://example.org/p3/sev#"
    warn = _write(
        tmp_path,
        "warn",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning .
""",
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:p "x" .',
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 0 ; sh:severity sh:Warning .
""",
        },
    )
    assert _severities(warn, "G0.ttl", "S0.ttl") == ["Warning"]
    wreport = _run(
        warn,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=WARN,
        out=tmp_path / "warn.json",
    )
    assert wreport["intervention_A"]["result_outcome"] == "CLEAR"
    assert wreport["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        wreport["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        wreport["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

    info = _write(
        tmp_path,
        "info",
        {
            "G0.ttl": warn.joinpath("G0.ttl").read_text(),
            "S0.ttl": warn.joinpath("S0.ttl")
            .read_text()
            .replace("Warning", "Info"),
            "GA.ttl": warn.joinpath("G0.ttl").read_text(),
            "SB.ttl": warn.joinpath("S0.ttl")
            .read_text()
            .replace("Warning", "Info"),
        },
    )
    assert _severities(info, "G0.ttl", "S0.ttl") == ["Info"]
    ireport = _run(
        info,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=INFO,
        out=tmp_path / "info.json",
    )
    assert ireport["intervention_A"]["result_outcome"] == "PERSIST"
    assert ireport["intervention_B"]["result_outcome"] == "PERSIST"
    assert (
        ireport["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_wrong_severity_does_not_designate(tmp_path: Path):
    ns = "http://example.org/p3/wrong#"
    case = _write(
        tmp_path,
        "wrong",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning .
""",
            "GA.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning .
""",
        },
    )
    results = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )["results"]
    with pytest.raises(DesignateError):
        select_designated(
            results,
            focus_key=ns + "N",
            path=ns + "p",
            component=COMP_MIN,
            severity=VIOL,
            source_shape=ns + "P",
        )

def test_severity_change_clears_designated_emits_new_residual(tmp_path: Path):
    ns = "http://example.org/p3/sevchg#"
    case = _write(
        tmp_path,
        "sevchg",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning .
""",
            "GA.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Violation .
""",
        },
    )
    assert _severities(case, "G0.ttl", "S0.ttl") == ["Warning"]
    assert _severities(case, "G0.ttl", "SB.ttl") == ["Violation"]
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=WARN,
        out=tmp_path / "sevchg.json",
    )
    assert report["intervention_A"]["result_outcome"] == "PERSIST"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    news = report["intervention_B"]["residual_results"]["new"]
    assert len(news) == 1
    assert news[0]["signature"][4] == VIOL

def test_mixed_warning_and_violation_residuals(tmp_path: Path):
    ns = "http://example.org/p3/mix#"
    case = _write(
        tmp_path,
        "mix",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P1 ; sh:property ex:P2 .
ex:P1 sh:path ex:a ; sh:minCount 1 ; sh:severity sh:Warning .
ex:P2 sh:path ex:b ; sh:minCount 1 .
""",
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:a "x" .',
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P1 ; sh:property ex:P2 .
ex:P1 sh:path ex:a ; sh:minCount 0 ; sh:severity sh:Warning .
ex:P2 sh:path ex:b ; sh:minCount 1 .
""",
        },
    )
    base = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )
    assert len(base["results"]) == 2
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "a",
        source_shape=ns + "P1",
        component=COMP_MIN,
        severity=WARN,
        out=tmp_path / "mix.json",
    )
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
    assert len(report["intervention_A"]["residual_results"]["persisted"]) == 1
    assert len(report["intervention_B"]["residual_results"]["persisted"]) == 1


def test_property_deactivation_clears_but_original_violated(tmp_path: Path):
    ns = "http://example.org/p3/deactp#"
    case = _write(
        tmp_path,
        "deactp",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:deactivated false .
""",
            "GA.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:deactivated true .
""",
        },
    )
    assert run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )["conforms"] is False
    assert run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "SB.ttl"), []
    )["conforms"] is True

    report = _run(
        case,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=VIOL,
        out=tmp_path / "deactp.json",
    )
    assert report["intervention_A"]["result_outcome"] == "PERSIST"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    assert report["intervention_B"]["target_membership"] == "RETAINED"

def test_node_shape_deactivation_anonymous_property(tmp_path: Path):
    ns = "http://example.org/p3/deactn#"
    case = _write(
        tmp_path,
        "deactn",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [
  sh:path ex:p ; sh:minCount 1
] .
""",
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:p "x" .',
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:deactivated true ; sh:property [
  sh:path ex:p ; sh:minCount 1
] .
""",
        },
    )
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "p",
        source_shape=None,
        component=COMP_MIN,
        severity=VIOL,
        out=tmp_path / "deactn.json",
    )
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

def test_sparql_constraint_deactivation(tmp_path: Path):
    ns = "http://example.org/p3/deacts#"
    case = _write(
        tmp_path,
        "deacts",
        {
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:sparql [
    sh:message "fail" ;
    sh:select \"\"\"SELECT $this WHERE {{ FILTER(true) }}\"\"\"
  ] .
""",
            "GA.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:sparql [
    sh:message "fail" ;
    sh:select \"\"\"SELECT $this WHERE {{ FILTER(true) }}\"\"\" ;
    sh:deactivated true
  ] .
""",
        },
    )
    assert run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "SB.ttl"), []
    )["conforms"] is True
    report = _run(
        case,
        focus=ns + "N",
        path="",
        source_shape=ns + "S",
        component=SPARQL,
        severity=VIOL,
        out=tmp_path / "deacts.json",
    )
    assert report["intervention_A"]["result_outcome"] == "PERSIST"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_other_focus_under_warning(tmp_path: Path):
    ns = "http://example.org/p3/of#"
    case = _write(
        tmp_path,
        "of",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T .
ex:M a ex:T .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T ; ex:p "x" .
ex:M a ex:T .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P sh:path ex:p ; sh:minCount 0 ; sh:severity sh:Warning .
""",
        },
    )
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "p",
        source_shape=ns + "P",
        component=COMP_MIN,
        severity=WARN,
        out=tmp_path / "of.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    others = {
        o["focus_key"]: o["result_outcome"]
        for o in report["intervention_A"]["other_focus_nodes"]
    }
    assert others.get(ns + "M") == "PERSIST"
