from rdflib import Graph, Literal, URIRef

from shacl_compare.diff import diff_graphs

def test_ground_diff_exact():
    before = Graph()
    after = Graph()
    s = URIRef("http://example.org/s")
    p = URIRef("http://example.org/p")
    before.add((s, p, Literal("a")))
    before.add((s, p, Literal("b")))
    after.add((s, p, Literal("a")))
    d = diff_graphs(before, after)
    assert d["diff_status"] == "RESOLVED"
    assert d["deletion_count"] == 1
    assert d["addition_count"] == 0

def test_blank_node_changed_is_ambiguous():
    before = Graph()
    after = Graph()
    before.parse(
        data="""
        @prefix ex: <http://example.org/> .
        ex:w ex:item [ ex:label "a", "b" ] .
        """,
        format="turtle",
    )
    after.parse(
        data="""
        @prefix ex: <http://example.org/> .
        ex:w ex:item [ ex:label "a" ] .
        """,
        format="turtle",
    )
    d = diff_graphs(before, after)
    assert d["diff_status"] == "AMBIGUOUS"
    assert d["rdf_triple_deletions"] == []
    assert d["rdf_triple_additions"] == []
    assert d["deletion_count"] is None

def test_blank_node_isomorphic_resolved_empty():
    g1 = Graph()
    g2 = Graph()
    ttl = """
    @prefix ex: <http://example.org/> .
    ex:w ex:item [ ex:label "a" ] .
    """
    g1.parse(data=ttl, format="turtle")
    g2.parse(data=ttl, format="turtle")
    d = diff_graphs(g1, g2)
    assert d["diff_status"] == "RESOLVED"
    assert d["unchanged"] is True
    assert d["deletion_count"] == 0
