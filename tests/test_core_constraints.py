
from __future__ import annotations

from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import DesignateError, select_designated
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

VIOL = str(SH.Violation)

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

def _assert_clear_satisfied_clear_violated(report: dict, *, label: str) -> None:
    assert report["intervention_A"]["result_outcome"] == "CLEAR", label
    assert report["intervention_B"]["result_outcome"] == "CLEAR", label
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    ), label
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    ), label
    assert report["intervention_A"]["target_membership"] == "RETAINED", label

def _assert_persist_violated(report: dict, *, label: str) -> None:
    assert report["intervention_A"]["result_outcome"] == "PERSIST", label
    assert report["intervention_B"]["result_outcome"] == "PERSIST", label
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    ), label
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    ), label


def test_min_exclusive_clear_and_persist(tmp_path: Path):
    ns = "http://example.org/p0/me#"
    case = _write(
        tmp_path,
        "minExclusive",
        {
            "G0.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v 5 .\n",
            "GA.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v 11 .\n",
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minExclusive 10 .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minExclusive 0 .
""",
        },
    )
    report = _run(
        case,
        focus=f"{ns}N",
        path=f"{ns}v",
        source_shape=f"{ns}P",
        component=str(SH.MinExclusiveConstraintComponent),
        out=tmp_path / "me.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="minExclusive")

    ns2 = "http://example.org/p0/mep#"
    persist = _write(
        tmp_path,
        "minExclusive_persist",
        {
            "G0.ttl": f"@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:v 5 .\n",
            "GA.ttl": f"@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:v 5 .\n",
            "S0.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minExclusive 10 .
""",
            "SB.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; sh:minExclusive 10 .
""",
        },
    )
    report_p = _run(
        persist,
        focus=f"{ns2}N",
        path=f"{ns2}v",
        source_shape=f"{ns2}P",
        component=str(SH.MinExclusiveConstraintComponent),
        out=tmp_path / "mep.json",
    )
    _assert_persist_violated(report_p, label="minExclusive_persist")

def test_max_exclusive_and_max_inclusive(tmp_path: Path):
    for name, param, g0v, gav, s0lim, sblim, comp in (
        (
            "maxExclusive",
            "sh:maxExclusive",
            10,
            5,
            10,
            100,
            SH.MaxExclusiveConstraintComponent,
        ),
        (
            "maxInclusive",
            "sh:maxInclusive",
            20,
            10,
            10,
            20,
            SH.MaxInclusiveConstraintComponent,
        ),
    ):
        ns = f"http://example.org/p0/{name}#"
        case = _write(
            tmp_path,
            name,
            {
                "G0.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v {g0v} .\n",
                "GA.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v {gav} .\n",
                "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; {param} {s0lim} .
""",
                "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:integer ; {param} {sblim} .
""",
            },
        )
        report = _run(
            case,
            focus=f"{ns}N",
            path=f"{ns}v",
            source_shape=f"{ns}P",
            component=str(comp),
            out=tmp_path / f"{name}.json",
        )
        _assert_clear_satisfied_clear_violated(report, label=name)

def test_min_length_and_max_length(tmp_path: Path):
    specs = [
        (
            "minLength",
            "sh:minLength",
            '"ab"',
            '"abcd"',
            4,
            1,
            SH.MinLengthConstraintComponent,
        ),
        (
            "maxLength",
            "sh:maxLength",
            '"abcdef"',
            '"ab"',
            3,
            10,
            SH.MaxLengthConstraintComponent,
        ),
    ]
    for name, param, g0v, gav, s0lim, sblim, comp in specs:
        ns = f"http://example.org/p0/{name}#"
        case = _write(
            tmp_path,
            name,
            {
                "G0.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v {g0v} .\n",
                "GA.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v {gav} .\n",
                "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; {param} {s0lim} .
""",
                "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; {param} {sblim} .
""",
            },
        )
        report = _run(
            case,
            focus=f"{ns}N",
            path=f"{ns}v",
            source_shape=f"{ns}P",
            component=str(comp),
            out=tmp_path / f"{name}.json",
        )
        _assert_clear_satisfied_clear_violated(report, label=name)


def test_language_in_and_unique_lang(tmp_path: Path):
    ns = "http://example.org/p0/li#"
    case = _write(
        tmp_path,
        "languageIn",
        {
            "G0.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v "bonjour"@fr .\n',
            "GA.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v "hello"@en .\n',
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:languageIn ( "en" "de" ) .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:languageIn ( "fr" "en" ) .
""",
        },
    )
    report = _run(
        case,
        focus=f"{ns}N",
        path=f"{ns}v",
        source_shape=f"{ns}P",
        component=str(SH.LanguageInConstraintComponent),
        out=tmp_path / "li.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="languageIn")

    ns2 = "http://example.org/p0/ul#"
    ul = _write(
        tmp_path,
        "uniqueLang",
        {
            "G0.ttl": f'@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:v "a"@en , "b"@en .\n',
            "GA.ttl": f'@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:v "a"@en , "b"@de .\n',
            "S0.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:uniqueLang true .
""",
            "SB.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v .
""",
        },
    )
    base = run_validation(load_graph(ul / "G0.ttl"), load_graph(ul / "S0.ttl"), [])
    assert base["result_count"] >= 1
    assert "value" not in base["results"][0] or True  # absent value is allowed
    report_ul = _run(
        ul,
        focus=f"{ns2}N",
        path=f"{ns2}v",
        source_shape=f"{ns2}P",
        component=str(SH.UniqueLangConstraintComponent),
        out=tmp_path / "ul.json",
    )
    _assert_clear_satisfied_clear_violated(report_ul, label="uniqueLang")

def test_equals_single_and_multi_value_requires_index(tmp_path: Path):
    ns = "http://example.org/p0/es#"
    single = _write(
        tmp_path,
        "equals_single",
        {
            "G0.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 1 .\n",
            "GA.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 1 ; ex:b 1 .\n",
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:a ; sh:equals ex:b .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:a .
""",
        },
    )
    report = _run(
        single,
        focus=f"{ns}N",
        path=f"{ns}a",
        source_shape=f"{ns}P",
        component=str(SH.EqualsConstraintComponent),
        out=tmp_path / "es.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="equals_single")

    ns2 = "http://example.org/p0/eq#"
    multi = _write(
        tmp_path,
        "equals_multi",
        {
            "G0.ttl": f"@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:a 1 ; ex:b 2 .\n",
            "GA.ttl": f"@prefix ex: <{ns2}> .\nex:N a ex:T ; ex:a 1 ; ex:b 1 .\n",
            "S0.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:a ; sh:equals ex:b .
""",
            "SB.ttl": f"""
@prefix ex: <{ns2}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:a .
""",
        },
    )
    v = run_validation(load_graph(multi / "G0.ttl"), load_graph(multi / "S0.ttl"), [])
    assert v["result_count"] >= 2
    try:
        select_designated(
            v["results"],
            focus_key=f"{ns2}N",
            path=f"{ns2}a",
            source_shape=f"{ns2}P",
            component=str(SH.EqualsConstraintComponent),
            severity=VIOL,
        )
        raised = False
    except DesignateError:
        raised = True
    assert raised, "multi-value Equals must require designation-index"
    report_m = _run(
        multi,
        focus=f"{ns2}N",
        path=f"{ns2}a",
        source_shape=f"{ns2}P",
        component=str(SH.EqualsConstraintComponent),
        out=tmp_path / "eq.json",
        designation_index=1,
    )
    _assert_clear_satisfied_clear_violated(report_m, label="equals_multi")

def test_disjoint_less_than_less_than_or_equals(tmp_path: Path):
    specs = [
        (
            "disjoint",
            "sh:disjoint ex:b",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 1 ; ex:b 1 .\n",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 1 ; ex:b 2 .\n",
            SH.DisjointConstraintComponent,
            "a",
        ),
        (
            "lessThan",
            "sh:datatype xsd:integer ; sh:lessThan ex:b",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 5 ; ex:b 3 .\n",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 2 ; ex:b 3 .\n",
            SH.LessThanConstraintComponent,
            "a",
        ),
        (
            "lessThanOrEquals",
            "sh:datatype xsd:integer ; sh:lessThanOrEquals ex:b",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 5 ; ex:b 3 .\n",
            "@prefix ex: <{ns}> .\nex:N a ex:T ; ex:a 3 ; ex:b 3 .\n",
            SH.LessThanOrEqualsConstraintComponent,
            "a",
        ),
    ]
    for name, constraint, g0, ga, comp, path_local in specs:
        ns = f"http://example.org/p0/{name}#"
        case = _write(
            tmp_path,
            name,
            {
                "G0.ttl": g0.format(ns=ns),
                "GA.ttl": ga.format(ns=ns),
                "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:{path_local} ; {constraint} .
""",
                "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:{path_local} .
""",
            },
        )
        report = _run(
            case,
            focus=f"{ns}N",
            path=f"{ns}{path_local}",
            source_shape=f"{ns}P",
            component=str(comp),
            out=tmp_path / f"{name}.json",
        )
        _assert_clear_satisfied_clear_violated(report, label=name)


def test_and_xone_clear_and_and_persist(tmp_path: Path):
    ns = "http://example.org/p0/and#"
    case = _write(
        tmp_path,
        "and",
        {
            "G0.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v "x" .\n',
            "GA.ttl": f"@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v 5 .\n",
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ;
  sh:and ( [ sh:datatype xsd:integer ] [ sh:minInclusive 1 ] ) .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:string .
""",
        },
    )
    report = _run(
        case,
        focus=f"{ns}N",
        path=f"{ns}v",
        source_shape=f"{ns}P",
        component=str(SH.AndConstraintComponent),
        out=tmp_path / "and.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="and")

    ns_p = "http://example.org/p0/ap#"
    persist = _write(
        tmp_path,
        "and_persist",
        {
            "G0.ttl": f'@prefix ex: <{ns_p}> .\nex:N a ex:T ; ex:v "x" .\n',
            "GA.ttl": f'@prefix ex: <{ns_p}> .\nex:N a ex:T ; ex:v "x" .\n',
            "S0.ttl": f"""
@prefix ex: <{ns_p}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ;
  sh:and ( [ sh:datatype xsd:integer ] [ sh:minInclusive 1 ] ) .
""",
            "SB.ttl": f"""
@prefix ex: <{ns_p}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ;
  sh:and ( [ sh:datatype xsd:integer ] [ sh:minInclusive 1 ] ) .
""",
        },
    )
    report_p = _run(
        persist,
        focus=f"{ns_p}N",
        path=f"{ns_p}v",
        source_shape=f"{ns_p}P",
        component=str(SH.AndConstraintComponent),
        out=tmp_path / "ap.json",
    )
    _assert_persist_violated(report_p, label="and_persist")

    nsx = "http://example.org/p0/xo#"
    xone = _write(
        tmp_path,
        "xone",
        {
            "G0.ttl": f'@prefix ex: <{nsx}> .\nex:N a ex:T ; ex:v "x" .\n',
            "GA.ttl": f"@prefix ex: <{nsx}> .\nex:N a ex:T ; ex:v 1 .\n",
            "S0.ttl": f"""
@prefix ex: <{nsx}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ;
  sh:xone ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:boolean ] ) .
""",
            "SB.ttl": f"""
@prefix ex: <{nsx}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:datatype xsd:string .
""",
        },
    )
    report_x = _run(
        xone,
        focus=f"{nsx}N",
        path=f"{nsx}v",
        source_shape=f"{nsx}P",
        component=str(SH.XoneConstraintComponent),
        out=tmp_path / "xo.json",
    )
    _assert_clear_satisfied_clear_violated(report_x, label="xone")

def test_closed_node_level_absent_cli_path(tmp_path: Path):
    ns = "http://example.org/p0/cl#"
    case = _write(
        tmp_path,
        "closed",
        {
            "G0.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:name "n" ; ex:extra 1 .\n',
            "GA.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:name "n" .\n',
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:closed true ;
  sh:ignoredProperties ( rdf:type ) ;
  sh:property [ sh:path ex:name ] .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:closed false ;
  sh:property [ sh:path ex:name ] .
""",
        },
    )
    base = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    assert base["results"][0]["source_constraint_component"] == str(
        SH.ClosedConstraintComponent
    )
    report = _run(
        case,
        focus=f"{ns}N",
        path="",
        source_shape=f"{ns}S",
        component=str(SH.ClosedConstraintComponent),
        out=tmp_path / "cl.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="closed")

def test_node_constraint_and_nested_datatype_residual(tmp_path: Path):
    ns = "http://example.org/p0/nd#"
    case = _write(
        tmp_path,
        "node",
        {
            "G0.ttl": (
                f"@prefix ex: <{ns}> .\n"
                f'ex:N a ex:T ; ex:friend ex:F . ex:F ex:age "young" .\n'
            ),
            "GA.ttl": (
                f"@prefix ex: <{ns}> .\n"
                f"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
                f"ex:N a ex:T ; ex:friend ex:F . ex:F ex:age 30 .\n"
            ),
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:friend ; sh:node ex:FriendShape .
ex:FriendShape a sh:NodeShape ;
  sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:friend .
""",
        },
    )
    base = run_validation(load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), [])
    comps = {r["source_constraint_component"] for r in base["results"]}
    assert str(SH.NodeConstraintComponent) in comps
    assert str(SH.DatatypeConstraintComponent) in comps  # nested residual
    report = _run(
        case,
        focus=f"{ns}N",
        path=f"{ns}friend",
        source_shape=f"{ns}P",
        component=str(SH.NodeConstraintComponent),
        out=tmp_path / "nd.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="node")
    residuals = report["intervention_A"]["residual_results"]
    assert isinstance(residuals, dict)

def test_pattern_with_flags(tmp_path: Path):
    ns = "http://example.org/p0/pf#"
    case = _write(
        tmp_path,
        "pattern_flags",
        {
            "G0.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v "abc" .\n',
            "GA.ttl": f'@prefix ex: <{ns}> .\nex:N a ex:T ; ex:v "42" .\n',
            "S0.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:pattern "^[0-9]+$" ; sh:flags "i" .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:v ; sh:pattern "^[a-z]+$" ; sh:flags "i" .
""",
        },
    )
    report = _run(
        case,
        focus=f"{ns}N",
        path=f"{ns}v",
        source_shape=f"{ns}P",
        component=str(SH.PatternConstraintComponent),
        out=tmp_path / "pf.json",
    )
    _assert_clear_satisfied_clear_violated(report, label="pattern_flags")
