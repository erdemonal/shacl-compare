
from __future__ import annotations

from pathlib import Path

import pytest
from rdflib.namespace import SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import (
    DesignateError,
    _component_parameter,
    evaluate_original_cardinality_on_focus,
    select_designated,
)
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

VIOL = str(SH.Violation)
QMIN = str(SH.QualifiedMinCountConstraintComponent)
QMAX = str(SH.QualifiedMaxCountConstraintComponent)
MIN = str(SH.MinCountConstraintComponent)
MAX = str(SH.MaxCountConstraintComponent)

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
    source_shape: str,
    component: str,
    out: Path,
    designation_index: int | None = None,
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
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
            designation_index=designation_index,
        )
    )

def _py_conforms(case: Path, data: str, shapes: str) -> tuple[bool, list[str]]:
    v = run_validation(load_graph(case / data), load_graph(case / shapes), [])
    comps = [
        str(r.get("source_constraint_component", "")).rsplit("#", 1)[-1]
        for r in v["results"]
    ]
    return v["conforms"], comps

def _assert_filter_only(report: dict, branch: str) -> None:
    o = report[branch]["original_constraint_evaluation"]
    assert o.get("cardinality_crosscheck_status") == "FILTER_ONLY_EVALUATED", branch
    assert (
        o.get("cardinality_crosscheck", {}).get("reason")
        == "unsupported_component_for_original_evaluation"
    ), branch


def test_qualified_components_not_mapped_to_ordinary_parameters():
    assert _component_parameter(QMIN) is None
    assert _component_parameter(QMAX) is None
    assert _component_parameter(MIN) == SH.minCount
    assert _component_parameter(MAX) == SH.maxCount

def test_qualified_not_designated_as_min_count(tmp_path: Path):
    ns = "http://example.org/qualified/guard#"
    case = _write(
        tmp_path,
        "guard",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:minCount 2 ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:minCount 2 ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 .
""",
        },
    )
    conforms, comps = _py_conforms(case, "G0.ttl", "S0.ttl")
    assert conforms is False
    assert comps == ["QualifiedMinCountConstraintComponent"]

    base_results = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )["results"]
    with pytest.raises(DesignateError):
        select_designated(
            base_results,
            focus_key=ns + "O",
            path=ns + "member",
            component=MIN,
            severity=VIOL,
            source_shape=ns + "MemberPS",
        )

    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "guard.json",
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
    _assert_filter_only(report, "intervention_A")


def test_qualified_min_count_clear_and_persist(tmp_path: Path):
    ns = "http://example.org/qualified/qmin#"
    clear = _write(
        tmp_path,
        "qmin_clear",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 .
""",
        },
    )
    assert _py_conforms(clear, "G0.ttl", "S0.ttl") == (
        False,
        ["QualifiedMinCountConstraintComponent"],
    )
    assert _py_conforms(clear, "GA.ttl", "S0.ttl")[0] is True
    assert _py_conforms(clear, "G0.ttl", "SB.ttl")[0] is True

    report = _run(
        clear,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "qmin_clear.json",
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
    assert report["intervention_A"]["target_membership"] == "RETAINED"
    _assert_filter_only(report, "intervention_A")
    _assert_filter_only(report, "intervention_B")

    persist = _write(
        tmp_path,
        "qmin_persist",
        {
            "G0.ttl": clear.joinpath("G0.ttl").read_text(),
            "S0.ttl": clear.joinpath("S0.ttl").read_text(),
            "GA.ttl": clear.joinpath("G0.ttl").read_text(),
            "SB.ttl": clear.joinpath("S0.ttl").read_text(),
        },
    )
    preport = _run(
        persist,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "qmin_persist.json",
    )
    assert preport["intervention_A"]["result_outcome"] == "PERSIST"
    assert preport["intervention_B"]["result_outcome"] == "PERSIST"
    assert (
        preport["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    assert (
        preport["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_qualified_min_b_clear_preserves_original_violated(tmp_path: Path):
    ns = "http://example.org/qualified/qminb#"
    case = _write(
        tmp_path,
        "qmin_b_only",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 .
""",
        },
    )
    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "qmin_b.json",
    )
    assert report["intervention_A"]["result_outcome"] == "PERSIST"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )


def test_qualified_max_count_clear_and_persist(tmp_path: Path):
    ns = "http://example.org/qualified/qmax#"
    clear = _write(
        tmp_path,
        "qmax_clear",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Employee .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMaxCount 1 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMaxCount 3 .
""",
        },
    )
    assert _py_conforms(clear, "G0.ttl", "S0.ttl") == (
        False,
        ["QualifiedMaxCountConstraintComponent"],
    )
    assert _py_conforms(clear, "GA.ttl", "S0.ttl")[0] is True
    assert _py_conforms(clear, "G0.ttl", "SB.ttl")[0] is True

    report = _run(
        clear,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMAX,
        out=tmp_path / "qmax_clear.json",
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
    _assert_filter_only(report, "intervention_A")

    persist = _write(
        tmp_path,
        "qmax_persist",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B .
ex:A a ex:Employee .
ex:B a ex:Employee .
""",
            "S0.ttl": clear.joinpath("S0.ttl").read_text(),
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Person .
""",
            "SB.ttl": clear.joinpath("S0.ttl").read_text(),
        },
    )
    preport = _run(
        persist,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMAX,
        out=tmp_path / "qmax_persist.json",
    )
    assert preport["intervention_A"]["result_outcome"] == "PERSIST"
    assert preport["intervention_B"]["result_outcome"] == "PERSIST"
    assert (
        preport["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )


def test_nested_qualified_value_shape(tmp_path: Path):
    ns = "http://example.org/qualified/nest#"
    case = _write(
        tmp_path,
        "nest",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B .
ex:A a ex:Employee ; ex:level 1 .
ex:B a ex:Employee ; ex:level 1 .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [
    sh:class ex:Employee ;
    sh:property [ sh:path ex:level ; sh:minInclusive 5 ]
  ] ;
  sh:qualifiedMinCount 1 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B .
ex:A a ex:Employee ; ex:level 5 .
ex:B a ex:Employee ; ex:level 1 .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 .
""",
        },
    )
    assert _py_conforms(case, "G0.ttl", "S0.ttl")[0] is False
    assert _py_conforms(case, "GA.ttl", "S0.ttl")[0] is True
    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "nest.json",
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

def test_qualified_value_shapes_disjoint_siblings(tmp_path: Path):
    ns = "http://example.org/qualified/dis#"
    case = _write(
        tmp_path,
        "dis",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B .
ex:A a ex:Employee, ex:Manager .
ex:B a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ;
  sh:property ex:EmpPS ; sh:property ex:MgrPS .
ex:EmpPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2 ;
  sh:qualifiedValueShapesDisjoint true .
ex:MgrPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Manager ] ;
  sh:qualifiedMinCount 1 ;
  sh:qualifiedValueShapesDisjoint true .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Manager .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ;
  sh:property ex:EmpPS ; sh:property ex:MgrPS .
ex:EmpPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 ;
  sh:qualifiedValueShapesDisjoint true .
ex:MgrPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Manager ] ;
  sh:qualifiedMinCount 1 ;
  sh:qualifiedValueShapesDisjoint true .
""",
        },
    )
    base = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    shapes = {r["source_shape"] for r in base["results"]}
    assert ns + "EmpPS" in shapes
    assert ns + "MgrPS" in shapes
    assert len(base["results"]) >= 2
    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "EmpPS",
        component=QMIN,
        out=tmp_path / "dis_emp.json",
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
    mreport = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MgrPS",
        component=QMIN,
        out=tmp_path / "dis_mgr.json",
    )
    assert mreport["intervention_A"]["result_outcome"] == "CLEAR"
    assert mreport["intervention_B"]["result_outcome"] == "PERSIST"

def test_anonymous_property_shape_qualified(tmp_path: Path):
    ns = "http://example.org/qualified/anon#"
    case = _write(
        tmp_path,
        "anon",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Person .
ex:C a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property [
  sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2
] .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B, ex:C .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:C a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property [
  sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1
] .
""",
        },
    )
    base = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    des = select_designated(
        base["results"],
        focus_key=ns + "O",
        path=ns + "member",
        component=QMIN,
        severity=VIOL,
    )
    assert not des["source_shape"].startswith("http")
    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=des["source_shape"],
        component=QMIN,
        out=tmp_path / "anon.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["shape_alignment"] == "ALIGNED"
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

def test_other_focus_residual_under_qualified(tmp_path: Path):
    ns = "http://example.org/qualified/of#"
    case = _write(
        tmp_path,
        "of",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A .
ex:A a ex:Employee .
ex:P a ex:Org ; ex:member ex:X .
ex:X a ex:Person .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 2 .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:O a ex:Org ; ex:member ex:A, ex:B .
ex:A a ex:Employee .
ex:B a ex:Employee .
ex:P a ex:Org ; ex:member ex:X .
ex:X a ex:Person .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:OrgShape a sh:NodeShape ; sh:targetClass ex:Org ; sh:property ex:MemberPS .
ex:MemberPS a sh:PropertyShape ; sh:path ex:member ;
  sh:qualifiedValueShape [ sh:class ex:Employee ] ;
  sh:qualifiedMinCount 1 .
""",
        },
    )
    report = _run(
        case,
        focus=ns + "O",
        path=ns + "member",
        source_shape=ns + "MemberPS",
        component=QMIN,
        out=tmp_path / "of.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    others_a = {
        o["focus_key"]: o["result_outcome"]
        for o in report["intervention_A"]["other_focus_nodes"]
    }
    assert others_a.get(ns + "P") == "PERSIST"

def test_qualified_cardinality_arithmetic_unsupported():
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import RDF

    ns = "http://example.org/qualified/arith#"
    EX = URIRef(ns)
    shapes = Graph()
    ps = EX + "MemberPS"
    shapes.add((ps, RDF.type, SH.PropertyShape))
    shapes.add((ps, SH.path, EX + "member"))
    shapes.add((ps, SH.qualifiedMinCount, Literal(2)))
    shapes.add((ps, SH.qualifiedValueShape, EX + "Emp"))

    result = evaluate_original_cardinality_on_focus(
        Graph(),
        shapes,
        focus_key=str(EX + "O"),
        path=str(EX + "member"),
        source_shape=str(ps),
        component=QMIN,
        focus_key_properties=[],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "unsupported_component_for_original_evaluation"
