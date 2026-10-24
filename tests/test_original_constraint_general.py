
from __future__ import annotations

import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main
from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import (
    combine_original_with_cardinality_crosscheck,
    evaluate_original_constraint_from_s0_results,
)

def _write_case(tmp: Path, name: str, files: dict[str, str]) -> Path:
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
) -> dict:
    cfg = CompareConfig(
        data_baseline=case / "G0.ttl",
        shapes_baseline=case / "S0.ttl",
        data_repair=case / "GA.ttl",
        shapes_revision=case / "SB.ttl",
        focus=focus,
        path=path,
        source_shape=source_shape,
        component=component,
        severity=str(SH.Violation),
        focus_key_properties=[],
        requirement_card=None,
        out=out,
    )
    return run_compare(cfg)

def test_datatype_original_satisfied_on_a_violated_on_b(tmp_path: Path):
    case = _write_case(
        tmp_path,
        "datatype",
        {
            "G0.ttl": '@prefix ex: <http://example.org/d#> .\nex:N a ex:T ; ex:v "abc" .\n',
            "GA.ttl": (
                "@prefix ex: <http://example.org/d#> .\n"
                "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
                "ex:N a ex:T ; ex:v 42 .\n"
            ),
            "S0.ttl": """
@prefix ex: <http://example.org/d#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer .
""",
            "SB.ttl": """
@prefix ex: <http://example.org/d#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:string .
""",
        },
    )
    report = _run(
        case,
        focus="http://example.org/d#N",
        path="http://example.org/d#v",
        source_shape="http://example.org/d#P",
        component=str(SH.DatatypeConstraintComponent),
        out=tmp_path / "out.json",
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
    assert report["intervention_B"]["original_constraint_evaluation"]["method"] == (
        "s0_validation_result_filter"
    )
    assert "original_constraint_semantics" in report["meta"]

def test_sibling_constraint_does_not_block_designated_original(tmp_path: Path):
    case = _write_case(
        tmp_path,
        "sibling",
        {
            "G0.ttl": (
                "@prefix ex: <http://example.org/sib#> .\n"
                'ex:N a ex:T ; ex:v "a" , "b" .\n'
            ),
            "GA.ttl": (
                "@prefix ex: <http://example.org/sib#> .\n"
                "ex:N a ex:T ; ex:v 1 .\n"
            ),
            "S0.ttl": """
@prefix ex: <http://example.org/sib#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:maxCount 1 ; sh:datatype xsd:string .
""",
            "SB.ttl": """
@prefix ex: <http://example.org/sib#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:maxCount 2 ; sh:datatype xsd:string .
""",
        },
    )
    report = _run(
        case,
        focus="http://example.org/sib#N",
        path="http://example.org/sib#v",
        source_shape="http://example.org/sib#P",
        component=str(SH.MaxCountConstraintComponent),
        out=tmp_path / "out.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["conforms"] is False
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "cardinality_crosscheck_status"
        ]
        == "AGREE"
    )

def test_core_components_matrix(tmp_path: Path):
    specs = [
        (
            "class",
            SH.ClassConstraintComponent,
            """
@prefix ex: <http://example.org/c#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:class ex:Person .
""",
            """
@prefix ex: <http://example.org/c#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:class ex:Other .
""",
            "@prefix ex: <http://example.org/c#> .\nex:N a ex:T ; ex:v ex:X . ex:X a ex:Other .\n",
            "@prefix ex: <http://example.org/c#> .\nex:N a ex:T ; ex:v ex:X . ex:X a ex:Person .\n",
        ),
        (
            "nodeKind",
            SH.NodeKindConstraintComponent,
            """
@prefix ex: <http://example.org/nk#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:nodeKind sh:IRI .
""",
            """
@prefix ex: <http://example.org/nk#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:nodeKind sh:Literal .
""",
            '@prefix ex: <http://example.org/nk#> .\nex:N a ex:T ; ex:v "lit" .\n',
            "@prefix ex: <http://example.org/nk#> .\nex:N a ex:T ; ex:v ex:OK .\n",
        ),
        (
            "pattern",
            SH.PatternConstraintComponent,
            """
@prefix ex: <http://example.org/pat#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:pattern "^[0-9]+$" .
""",
            """
@prefix ex: <http://example.org/pat#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:pattern "^[a-z]+$" .
""",
            '@prefix ex: <http://example.org/pat#> .\nex:N a ex:T ; ex:v "abc" .\n',
            '@prefix ex: <http://example.org/pat#> .\nex:N a ex:T ; ex:v "42" .\n',
        ),
        (
            "hasValue",
            SH.HasValueConstraintComponent,
            """
@prefix ex: <http://example.org/hv#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:hasValue ex:Required .
""",
            """
@prefix ex: <http://example.org/hv#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:hasValue ex:Other .
""",
            "@prefix ex: <http://example.org/hv#> .\nex:N a ex:T ; ex:v ex:Other .\n",
            "@prefix ex: <http://example.org/hv#> .\nex:N a ex:T ; ex:v ex:Required .\n",
        ),
        (
            "in",
            SH.InConstraintComponent,
            """
@prefix ex: <http://example.org/in#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:in ( "a" "b" ) .
""",
            """
@prefix ex: <http://example.org/in#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:in ( "z" ) .
""",
            '@prefix ex: <http://example.org/in#> .\nex:N a ex:T ; ex:v "z" .\n',
            '@prefix ex: <http://example.org/in#> .\nex:N a ex:T ; ex:v "a" .\n',
        ),
        (
            "minInclusive",
            SH.MinInclusiveConstraintComponent,
            """
@prefix ex: <http://example.org/mi#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minInclusive 10 .
""",
            """
@prefix ex: <http://example.org/mi#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minInclusive 0 .
""",
            "@prefix ex: <http://example.org/mi#> .\nex:N a ex:T ; ex:v 3 .\n",
            "@prefix ex: <http://example.org/mi#> .\nex:N a ex:T ; ex:v 10 .\n",
        ),
        (
            "or",
            SH.OrConstraintComponent,
            """
@prefix ex: <http://example.org/or#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ;
  sh:or ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:boolean ] ) .
""",
            """
@prefix ex: <http://example.org/or#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:string .
""",
            '@prefix ex: <http://example.org/or#> .\nex:N a ex:T ; ex:v "x" .\n',
            "@prefix ex: <http://example.org/or#> .\nex:N a ex:T ; ex:v 1 .\n",
        ),
    ]

    for name, component, s0, sb, g0, ga in specs:
        ns = {
            "class": "c",
            "nodeKind": "nk",
            "pattern": "pat",
            "hasValue": "hv",
            "in": "in",
            "minInclusive": "mi",
            "or": "or",
        }[name]
        case = _write_case(
            tmp_path,
            name,
            {"G0.ttl": g0, "GA.ttl": ga, "S0.ttl": s0, "SB.ttl": sb},
        )
        report = _run(
            case,
            focus=f"http://example.org/{ns}#N",
            path=f"http://example.org/{ns}#v",
            source_shape=f"http://example.org/{ns}#P",
            component=str(component),
            out=tmp_path / f"{name}.json",
        )
        assert report["intervention_A"]["result_outcome"] == "CLEAR", name
        assert (
            report["intervention_A"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "SATISFIED"
        ), name
        assert (
            report["intervention_B"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "VIOLATED"
        ), name

def test_target_loss_still_not_evaluated(tmp_path: Path):
    fix = Path(__file__).parent / "fixtures" / "target_loss"
    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(fix / "G0.ttl"),
            "--shapes-baseline",
            str(fix / "S0.ttl"),
            "--data-repair",
            str(fix / "GA.ttl"),
            "--shapes-revision",
            str(fix / "SB.ttl"),
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
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "NOT_EVALUATED"
    )
    assert (
        report["intervention_A"]["original_constraint_evaluation"]["reason"]
        == "focus_not_targeted"
    )

def test_sensor_datatype_gains_original_eval(tmp_path: Path):
    fix = Path(__file__).parent / "fixtures" / "sensor_datatype"
    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(fix / "G0.ttl"),
            "--shapes-baseline",
            str(fix / "S0.ttl"),
            "--data-repair",
            str(fix / "GA.ttl"),
            "--shapes-revision",
            str(fix / "SB.ttl"),
            "--focus",
            "http://example.org/iot#SensorA",
            "--path",
            "http://example.org/iot#reading",
            "--source-shape",
            "http://example.org/iot#SensorShape-reading",
            "--component",
            str(SH.DatatypeConstraintComponent),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
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

def test_anonymous_maxcount_original_still_works(tmp_path: Path):
    fix = Path(__file__).parent / "fixtures" / "anonymous_maxcount"
    cfg = CompareConfig(
        data_baseline=fix / "G0.ttl",
        shapes_baseline=fix / "S0.ttl",
        data_repair=fix / "GA.ttl",
        shapes_revision=fix / "SB.ttl",
        focus="http://example.org/anon#Item1",
        path="http://example.org/anon#code",
        source_shape=None,
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
        focus_key_properties=[],
        requirement_card=None,
        out=tmp_path / "out.json",
    )
    report = run_compare(cfg)
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
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "cardinality_crosscheck_status"
        ]
        == "AGREE"
    )

def test_cardinality_disagreement_yields_not_evaluated():
    vr = {
        "original_constraint_evaluation": "SATISFIED",
        "method": "s0_validation_result_filter",
    }
    card = {
        "original_constraint_evaluation": "VIOLATED",
        "parameter": str(SH.maxCount),
        "expected": 1,
        "observed_value_count": 2,
    }
    out = combine_original_with_cardinality_crosscheck(vr, card)
    assert out["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert out["reason"] == "cardinality_and_s0_result_filter_disagree"

def test_sparql_component_not_evaluated_without_fingerprint():
    result = evaluate_original_constraint_from_s0_results(
        [],
        focus_key="http://example.org/x#N",
        path="",
        source_shape="http://example.org/x#S",
        component=str(SH.SPARQLConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        sparql_fingerprint=None,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert "sparql_constraint_fingerprint_unavailable" in result["reason"]

def test_sparql_component_satisfied_with_fingerprint():
    result = evaluate_original_constraint_from_s0_results(
        [],
        focus_key="http://example.org/x#N",
        path="",
        source_shape="http://example.org/x#S",
        component=str(SH.SPARQLConstraintComponent),
        severity=str(SH.Violation),
        targeted=True,
        sparql_fingerprint="SPARQL:select:SELECT $this WHERE { FILTER (false) }|prefixes:",
    )
    assert result["original_constraint_evaluation"] == "SATISFIED"

def test_b_alignment_failure_still_reports_original_via_baseline(tmp_path: Path):
    case = _write_case(
        tmp_path,
        "cpath",
        {
            "G0.ttl": (
                "@prefix ex: <http://example.org/cp#> .\n"
                'ex:N a ex:T ; ex:knows ex:A . ex:A ex:email "a" , "b" .\n'
            ),
            "GA.ttl": (
                "@prefix ex: <http://example.org/cp#> .\n"
                'ex:N a ex:T ; ex:knows ex:A . ex:A ex:email "a" .\n'
            ),
            "S0.ttl": """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ( ex:knows ex:email ) ; sh:maxCount 1 .
""",
            "SB.ttl": """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ( ex:knows ex:mail ) ; sh:maxCount 2 .
""",
        },
    )
    from shacl_compare.graph_io import load_graph
    from shacl_compare.validation import run_validation

    base = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    row = base["results"][0]
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=row["focus_key"],
            path=row["result_path"],
            source_shape=row["source_shape"],
            component=row["source_constraint_component"],
            severity=row.get("severity") or str(SH.Violation),
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "out.json",
        )
    )
    assert report["intervention_B"]["result_outcome"] == "NOT_COMPARABLE"
    assert report["intervention_B"]["shape_alignment"] == "UNRESOLVED"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
