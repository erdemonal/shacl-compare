from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.designate import (
    evaluate_original_cardinality_on_focus,
    match_designated_after,
)
from shacl_compare.terms import node_focus_key


def test_no_soft_match_to_different_blank_focus():
    baseline_key = "bnode[type=http://example.org/Item|http://example.org/label=a,b]"
    other = {
        "focus_key": "bnode[type=http://example.org/Item|http://example.org/label=x,y]",
        "result_path": "http://example.org/label",
        "source_shape": "http://example.org/Shape",
        "source_constraint_component": str(SH.MaxCountConstraintComponent),
        "severity": str(SH.Violation),
    }
    matches, mode = match_designated_after(
        [other],
        focus_key=baseline_key,
        path="http://example.org/label",
        source_shape="http://example.org/Shape",
        component=str(SH.MaxCountConstraintComponent),
        severity=str(SH.Violation),
    )
    assert matches == []
    assert mode == "blank_focus_key_unmatched"


def test_resolve_focus_ambiguous_duplicate_content_keys():
    g = Graph()
    p = URIRef("http://example.org/label")
    a, b = BNode(), BNode()
    for node, val in ((a, "same"), (b, "same")):
        g.add((node, RDF.type, URIRef("http://example.org/Item")))
        g.add((node, p, Literal(val)))
    key = node_focus_key(g, a, [p])
    assert node_focus_key(g, b, [p]) == key

    result = evaluate_original_cardinality_on_focus(
        g,
        Graph(),
        focus_key=key,
        path=str(p),
        source_shape="http://example.org/Shape",
        component=str(SH.MaxCountConstraintComponent),
        focus_key_properties=[p],
        targeted=True,
    )
    # shapes graph empty → parameter missing; first ensure resolve path is safe:
    # re-call with a shapes graph that has maxCount so resolution is exercised.
    shapes = Graph()
    shape = URIRef("http://example.org/Shape")
    shapes.add((shape, SH.maxCount, Literal(1)))
    result = evaluate_original_cardinality_on_focus(
        g,
        shapes,
        focus_key=key,
        path=str(p),
        source_shape=str(shape),
        component=str(SH.MaxCountConstraintComponent),
        focus_key_properties=[p],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "ambiguous_focus_key_multiple_nodes"
