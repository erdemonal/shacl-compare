
from __future__ import annotations

from pathlib import Path

import pytest
from rdflib.namespace import SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.custom_constraint_components import (
    CUSTOM_CC_PREFIX,
    custom_cc_fingerprint,
)
from shacl_compare.designate import DesignateError
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

VIOL = str(SH.Violation)
MIN = str(SH.MinCountConstraintComponent)

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
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )

def _lang_select_shapes(ns: str, *, lang: str, deactivated: bool = False) -> str:
    deact = " ; sh:deactivated true" if deactivated else ""
    return f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponent a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:propertyValidator ex:hasLang .

ex:hasLang a sh:SPARQLSelectValidator ;
  sh:message "language mismatch" ;
  sh:select \"\"\"
    SELECT $this ?value
    WHERE {{
      $this $PATH ?value .
      FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))
    }}
  \"\"\" .

ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "{lang}"{deact} .
"""

def _lang_ask_shapes(ns: str, *, lang: str, deactivated: bool = False) -> str:
    deact = " ; sh:deactivated true" if deactivated else ""
    return f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponentAsk a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:validator [
    a sh:SPARQLAskValidator ;
    sh:message "language mismatch" ;
    sh:ask \"\"\"ASK {{ FILTER (isLiteral($value) && langMatches(lang($value), $lang)) }}\"\"\"
  ] .

ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "{lang}"{deact} .
"""


def test_select_custom_cc_clear_and_persist(tmp_path: Path):
    ns = "http://example.org/p4/sel#"
    comp = ns + "LanguageConstraintComponent"
    clear = _write(
        tmp_path,
        "sel_clear",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": _lang_select_shapes(ns, lang="en"),
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "hello"@en .',
            "SB.ttl": _lang_select_shapes(ns, lang="fr"),
        },
    )
    base = run_validation(
        load_graph(clear / "G0.ttl"), load_graph(clear / "S0.ttl"), []
    )
    assert base["conforms"] is False
    assert base["results"][0]["source_constraint_component"] == comp
    fp = base["results"][0].get("sparql_fingerprint")
    assert fp and fp.startswith(CUSTOM_CC_PREFIX)
    assert 'lang="en"' in fp
    assert "select:" in fp

    assert run_validation(
        load_graph(clear / "GA.ttl"), load_graph(clear / "S0.ttl"), []
    )["conforms"] is True
    assert run_validation(
        load_graph(clear / "G0.ttl"), load_graph(clear / "SB.ttl"), []
    )["conforms"] is True

    report = _run(
        clear,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "sel_clear.json",
    )
    assert report["designated"]["sparql_fingerprint"] == fp
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

    persist = _write(
        tmp_path,
        "sel_persist",
        {
            "G0.ttl": clear.joinpath("G0.ttl").read_text(),
            "S0.ttl": clear.joinpath("S0.ttl").read_text(),
            "GA.ttl": clear.joinpath("G0.ttl").read_text(),
            "SB.ttl": clear.joinpath("S0.ttl").read_text(),
        },
    )
    preport = _run(
        persist,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "sel_persist.json",
    )
    assert preport["intervention_A"]["result_outcome"] == "PERSIST"
    assert preport["intervention_B"]["result_outcome"] == "PERSIST"
    assert (
        preport["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_select_parameter_change_is_new_instance_not_persist(tmp_path: Path):
    ns = "http://example.org/p4/param#"
    comp = ns + "LanguageConstraintComponent"
    case = _write(
        tmp_path,
        "param",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": _lang_select_shapes(ns, lang="en"),
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "SB.ttl": _lang_select_shapes(ns, lang="de"),
        },
    )
    assert run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "SB.ttl"), []
    )["conforms"] is False
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "param.json",
    )
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    news = report["intervention_B"]["residual_results"]["new"]
    assert len(news) == 1
    assert any("lang=\"de\"" in str(part) for part in news[0]["signature"])

def test_select_query_revision_clears_designated(tmp_path: Path):
    ns = "http://example.org/p4/qrev#"
    comp = ns + "LanguageConstraintComponent"
    s0 = _lang_select_shapes(ns, lang="en")
    sb = s0.replace(
        "FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))",
        "FILTER (true)",
    )
    case = _write(
        tmp_path,
        "qrev",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": s0,
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "SB.ttl": sb,
        },
    )
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "qrev.json",
    )
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )


def test_ask_custom_cc_clear_via_repair_and_deactivation(tmp_path: Path):
    ns = "http://example.org/p4/ask#"
    comp = ns + "LanguageConstraintComponentAsk"
    case = _write(
        tmp_path,
        "ask",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": _lang_ask_shapes(ns, lang="en"),
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "hello"@en .',
            "SB.ttl": _lang_ask_shapes(ns, lang="en", deactivated=True),
        },
    )
    base = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )
    assert base["conforms"] is False
    fp = base["results"][0].get("sparql_fingerprint")
    assert fp and "ask:" in fp
    assert run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "SB.ttl"), []
    )["conforms"] is True

    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "ask.json",
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
    assert not any(
        "sh_ask_unsupported" in u for u in report.get("undetermined", [])
    )


def test_two_invocations_different_params_require_distinct_fingerprints(
    tmp_path: Path,
):
    ns = "http://example.org/p4/multi#"
    comp = ns + "LanguageConstraintComponent"
    case = _write(
        tmp_path,
        "multi",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T ;
  ex:label "bonjour"@fr ;
  ex:title "hallo"@de .
""",
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponent a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:propertyValidator ex:hasLang .

ex:hasLang a sh:SPARQLSelectValidator ;
  sh:message "language mismatch" ;
  sh:select \"\"\"
    SELECT $this ?value WHERE {{
      $this $PATH ?value .
      FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))
    }}
  \"\"\" .

ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:property ex:LabelPS ; sh:property ex:TitlePS .
ex:LabelPS a sh:PropertyShape ; sh:path ex:label ; ex:lang "en" .
ex:TitlePS a sh:PropertyShape ; sh:path ex:title ; ex:lang "en" .
""",
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T ;
  ex:label "hello"@en ;
  ex:title "hallo"@de .
""",
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponent a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:propertyValidator ex:hasLang .

ex:hasLang a sh:SPARQLSelectValidator ;
  sh:message "language mismatch" ;
  sh:select \"\"\"
    SELECT $this ?value WHERE {{
      $this $PATH ?value .
      FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))
    }}
  \"\"\" .

ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:property ex:LabelPS ; sh:property ex:TitlePS .
ex:LabelPS a sh:PropertyShape ; sh:path ex:label ; ex:lang "fr" .
ex:TitlePS a sh:PropertyShape ; sh:path ex:title ; ex:lang "en" .
""",
        },
    )
    base = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )
    assert len(base["results"]) >= 2
    fps = {r["sparql_fingerprint"] for r in base["results"]}
    assert len(fps) == 1  # same lang="en" binding text on both shapes
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "LabelPS",
        component=comp,
        out=tmp_path / "multi.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert len(report["intervention_A"]["residual_results"]["persisted"]) >= 1

def test_custom_cc_with_core_mincount_interaction(tmp_path: Path):
    ns = "http://example.org/p4/core#"
    comp = ns + "LanguageConstraintComponent"
    case = _write(
        tmp_path,
        "core",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": _lang_select_shapes(ns, lang="en").replace(
                'ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "en" .',
                'ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "en" ; sh:minCount 1 .',
            ),
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "hello"@en .',
            "SB.ttl": _lang_select_shapes(ns, lang="fr").replace(
                'ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "fr" .',
                'ex:P a sh:PropertyShape ; sh:path ex:label ; ex:lang "fr" ; sh:minCount 1 .',
            ),
        },
    )
    base = run_validation(
        load_graph(case / "G0.ttl"), load_graph(case / "S0.ttl"), []
    )
    comps = {r["source_constraint_component"] for r in base["results"]}
    assert comp in comps
    assert MIN not in comps

    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "core.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"

def test_anonymous_property_shape_custom_cc(tmp_path: Path):
    ns = "http://example.org/p4/anon#"
    comp = ns + "LanguageConstraintComponent"
    case = _write(
        tmp_path,
        "anon",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponent a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:propertyValidator ex:hasLang .

ex:hasLang a sh:SPARQLSelectValidator ;
  sh:message "language mismatch" ;
  sh:select \"\"\"
    SELECT $this ?value WHERE {{
      $this $PATH ?value .
      FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))
    }}
  \"\"\" .

ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [
  sh:path ex:label ; ex:lang "en"
] .
""",
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "hello"@en .',
            "SB.ttl": f"""
@prefix ex: <{ns}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:LanguageConstraintComponent a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lang ; sh:datatype xsd:string ] ;
  sh:propertyValidator ex:hasLang .

ex:hasLang a sh:SPARQLSelectValidator ;
  sh:message "language mismatch" ;
  sh:select \"\"\"
    SELECT $this ?value WHERE {{
      $this $PATH ?value .
      FILTER (!isLiteral(?value) || !langMatches(lang(?value), $lang))
    }}
  \"\"\" .

ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [
  sh:path ex:label ; ex:lang "fr"
] .
""",
        },
    )
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=None,
        component=comp,
        out=tmp_path / "anon.json",
    )
    assert report["designated"]["sparql_fingerprint"].startswith(CUSTOM_CC_PREFIX)
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_other_focus_under_custom_cc(tmp_path: Path):
    ns = "http://example.org/p4/of#"
    comp = ns + "LanguageConstraintComponent"
    case = _write(
        tmp_path,
        "of",
        {
            "G0.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T ; ex:label "bonjour"@fr .
ex:M a ex:T ; ex:label "ciao"@it .
""",
            "S0.ttl": _lang_select_shapes(ns, lang="en"),
            "GA.ttl": f"""
@prefix ex: <{ns}> .
ex:N a ex:T ; ex:label "hello"@en .
ex:M a ex:T ; ex:label "ciao"@it .
""",
            "SB.ttl": _lang_select_shapes(ns, lang="fr"),
        },
    )
    report = _run(
        case,
        focus=ns + "N",
        path=ns + "label",
        source_shape=ns + "P",
        component=comp,
        out=tmp_path / "of.json",
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    others = {
        o["focus_key"]: o["result_outcome"]
        for o in report["intervention_A"]["other_focus_nodes"]
    }
    assert others.get(ns + "M") == "PERSIST"

def test_fingerprint_helper_rejects_unknown_component(tmp_path: Path):
    ns = "http://example.org/p4/fp#"
    case = _write(
        tmp_path,
        "fp",
        {
            "S0.ttl": _lang_select_shapes(ns, lang="en"),
            "G0.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "GA.ttl": f"@prefix ex: <{ns}> . ex:N a ex:T .",
            "SB.ttl": _lang_select_shapes(ns, lang="en"),
        },
    )
    s0 = load_graph(case / "S0.ttl")
    assert custom_cc_fingerprint(s0, ns + "LanguageConstraintComponent", ns + "P")
    assert (
        custom_cc_fingerprint(s0, str(SH.MinCountConstraintComponent), ns + "P")
        is None
    )

def test_wrong_component_does_not_designate_as_sparql_constraint(tmp_path: Path):
    ns = "http://example.org/p4/wrong#"
    case = _write(
        tmp_path,
        "wrong",
        {
            "G0.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "S0.ttl": _lang_select_shapes(ns, lang="en"),
            "GA.ttl": f'@prefix ex: <{ns}> . ex:N a ex:T ; ex:label "bonjour"@fr .',
            "SB.ttl": _lang_select_shapes(ns, lang="en"),
        },
    )
    with pytest.raises(DesignateError):
        _run(
            case,
            focus=ns + "N",
            path=ns + "label",
            source_shape=ns + "P",
            component=str(SH.SPARQLConstraintComponent),
            out=tmp_path / "wrong.json",
        )
