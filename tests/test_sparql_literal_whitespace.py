
from __future__ import annotations

from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import DesignateError, select_designated
from shacl_compare.graph_io import load_graph
from shacl_compare.sparql_constraints import (
    SPARQL_CONSTRAINT_COMPONENT,
    normalize_sparql_query,
    sparql_constraint_fingerprint,
)
from shacl_compare.validation import run_validation

EX = URIRef("http://example.org/audit#")
COMP = SPARQL_CONSTRAINT_COMPONENT
VIOL = str(SH.Violation)
FIX = Path(__file__).parent / "fixtures" / "sparql_literal_whitespace"

def _fp(query: str, *, prefixes: list[tuple[str, str]] | None = None) -> str:
    g = Graph()
    c = BNode()
    g.add((c, SH.select, Literal(query)))
    if prefixes:
        pref_root = BNode()
        g.add((c, SH.prefixes, pref_root))
        for pfx, ns in prefixes:
            d = BNode()
            g.add((pref_root, SH.declare, d))
            g.add((d, SH.prefix, Literal(pfx)))
            g.add((d, SH.namespace, URIRef(ns)))
    fp = sparql_constraint_fingerprint(g, c)
    assert fp is not None
    return fp

def test_literal_internal_whitespace_distinct():
    q1 = 'SELECT $this WHERE { $this <http://example.org/audit#label> ?l . FILTER(?l = "hello  world") }'
    q2 = 'SELECT $this WHERE { $this <http://example.org/audit#label> ?l . FILTER(?l = "hello world") }'
    assert normalize_sparql_query(q1) != normalize_sparql_query(q2)
    assert _fp(q1) != _fp(q2)

def test_escaped_quotes_preserved():
    q1 = r'SELECT $this WHERE { FILTER(?l = "say \"hi\"") }'
    q2 = r'SELECT $this WHERE { FILTER(?l = "say \"hi\" ") }'
    assert _fp(q1) != _fp(q2)
    q1b = r'SELECT $this WHERE { FILTER(?l = "say \"hi\"") }'
    q1c = r'SELECT  $this  WHERE  {  FILTER(?l = "say \"hi\"")  }'
    assert _fp(q1b) == _fp(q1c)

def test_tabs_and_newlines_inside_literals_preserved():
    q_tab = 'SELECT $this WHERE { FILTER(?l = "a\tb") }'
    q_space = 'SELECT $this WHERE { FILTER(?l = "a b") }'
    q_nl = 'SELECT $this WHERE { FILTER(?l = "a\nb") }'
    assert _fp(q_tab) != _fp(q_space)
    assert _fp(q_nl) != _fp(q_space)
    assert _fp(q_tab) != _fp(q_nl)

def test_multiline_triple_quoted_literal_preserved():
    q1 = 'SELECT $this WHERE { FILTER(?l = """line1\nline2""") }'
    q2 = 'SELECT $this WHERE { FILTER(?l = """line1\nline2 """) }'
    assert _fp(q1) != _fp(q2)

def test_comment_difference_not_silently_merged():
    q1 = "SELECT $this WHERE { FILTER(true) } # alpha\n"
    q2 = "SELECT $this WHERE { FILTER(true) } # beta\n"
    assert normalize_sparql_query(q1) != normalize_sparql_query(q2)
    assert _fp(q1) != _fp(q2)

def test_formatting_whitespace_outside_literals():
    q1 = "SELECT  $this\nWHERE {\n  FILTER(true)\n}"
    q2 = "SELECT $this WHERE { FILTER(true) }"
    assert normalize_sparql_query(q1) == normalize_sparql_query(q2)
    assert _fp(q1) == _fp(q2)

def test_keyword_case_not_folded():
    assert _fp("SELECT $this WHERE { FILTER(true) }") != _fp(
        "select $this where { filter(true) }"
    )

def test_prefix_declarations_affect_identity_not_message():
    q = 'SELECT $this WHERE { FILTER(true) }'
    fp_a = _fp(q, prefixes=[("ex", "http://example.org/audit#")])
    fp_b = _fp(q, prefixes=[("ex2", "http://example.org/audit#")])
    assert fp_a != fp_b
    g = Graph()
    c = BNode()
    g.add((c, SH.select, Literal(q)))
    g.add((c, SH.message, Literal("one")))
    fp1 = sparql_constraint_fingerprint(g, c)
    g2 = Graph()
    c2 = BNode()
    g2.add((c2, SH.select, Literal(q)))
    g2.add((c2, SH.message, Literal("two")))
    fp2 = sparql_constraint_fingerprint(g2, c2)
    assert fp1 == fp2

def test_literal_whitespace_compare_clear(tmp_path: Path):
    case = FIX
    assert (case / "S0.ttl").is_file()
    report = run_compare(
        CompareConfig(
            data_baseline=case / "G0.ttl",
            shapes_baseline=case / "S0.ttl",
            data_repair=case / "GA.ttl",
            shapes_revision=case / "SB.ttl",
            focus=str(EX + "N"),
            path="",
            source_shape=str(EX + "S"),
            component=COMP,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "a1_full.json",
        )
    )
    fp = report["designated"]["sparql_fingerprint"]
    assert "hello  world" in fp  # two spaces preserved
    assert report["intervention_A"]["result_outcome"] == "PERSIST"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_duplicate_queries_require_index():
    q = 'SELECT $this WHERE { FILTER NOT EXISTS { $this <http://example.org/audit#email> ?e } }'
    g0 = Graph()
    g0.add((EX + "N", RDF.type, EX + "T"))
    s0 = Graph()
    shape = EX + "S"
    s0.add((shape, RDF.type, SH.NodeShape))
    s0.add((shape, SH.targetClass, EX + "T"))
    for _ in range(2):
        c = BNode()
        s0.add((shape, SH.sparql, c))
        s0.add((c, SH.select, Literal(q)))
    v = run_validation(g0, s0, [])
    assert v["result_count"] >= 2
    fps = {r.get("sparql_fingerprint") for r in v["results"]}
    assert len(fps) == 1
    try:
        select_designated(
            v["results"],
            focus_key=str(EX + "N"),
            path="",
            source_shape=str(EX + "S"),
            component=COMP,
            severity=VIOL,
        )
        raised = False
    except DesignateError:
        raised = True
    assert raised
    chosen = select_designated(
        v["results"],
        focus_key=str(EX + "N"),
        path="",
        source_shape=str(EX + "S"),
        component=COMP,
        severity=VIOL,
        designation_index=1,
    )
    assert chosen.get("sparql_fingerprint")

def test_near_duplicate_literals_need_index():
    g0 = Graph()
    g0.add((EX + "N", RDF.type, EX + "T"))
    s0 = Graph()
    shape = EX + "S"
    s0.add((shape, RDF.type, SH.NodeShape))
    s0.add((shape, SH.targetClass, EX + "T"))
    for lit in ('"hello  world"', '"hello world"'):
        c = BNode()
        s0.add((shape, SH.sparql, c))
        s0.add(
            (
                c,
                SH.select,
                Literal(
                    f"SELECT $this WHERE {{ "
                    f"FILTER NOT EXISTS {{ $this <http://example.org/audit#label> {lit} }} }}"
                ),
            )
        )
    v = run_validation(g0, s0, [])
    fps = {r.get("sparql_fingerprint") for r in v["results"]}
    assert len(fps) == 2
    try:
        select_designated(
            v["results"],
            focus_key=str(EX + "N"),
            path="",
            source_shape=str(EX + "S"),
            component=COMP,
            severity=VIOL,
        )
        ok_without = True
    except DesignateError:
        ok_without = False
    assert ok_without is False
