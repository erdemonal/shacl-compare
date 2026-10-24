from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SH, XSD

from shacl_compare.designate import align_source_shape

EX = URIRef("http://example.org/ns#")

def _baseline():
    g = Graph()
    parent = EX + "PersonShape"
    prop = EX + "PersonShape-firstName"
    g.add((parent, RDF.type, SH.NodeShape))
    g.add((parent, SH.property, prop))
    g.add((prop, SH.path, EX + "firstName"))
    g.add((prop, SH.datatype, XSD.string))
    g.add((prop, SH.maxCount, Literal(1)))
    return g, str(prop), str(EX + "firstName")

def test_iri_present_but_path_changed_is_unresolved():
    base, prop, path = _baseline()
    after = Graph()
    for t in base:
        after.add(t)
    after.remove((URIRef(prop), SH.path, URIRef(path)))
    after.add((URIRef(prop), SH.path, EX + "lastName"))
    result = align_source_shape(
        base, after, prop, path, str(SH.MaxCountConstraintComponent)
    )
    assert result["shape_alignment"] == "UNRESOLVED"
    assert "path" in result["reason"]

def test_iri_only_as_object_reference_is_unresolved():
    base, prop, path = _baseline()
    after = Graph()
    after.add((EX + "Other", SH.property, URIRef(prop)))
    result = align_source_shape(
        base, after, prop, path, str(SH.MaxCountConstraintComponent)
    )
    assert result["shape_alignment"] == "UNRESOLVED"

def test_same_iri_path_parent_aligned_when_maxcount_deleted():
    base, prop, path = _baseline()
    after = Graph()
    for t in base:
        after.add(t)
    after.remove((URIRef(prop), SH.maxCount, Literal(1)))
    result = align_source_shape(
        base, after, prop, path, str(SH.MaxCountConstraintComponent)
    )
    assert result["shape_alignment"] == "ALIGNED"
    assert result["aligned_source_shape"] == prop
    assert result.get("constraint_parameter_status") == "ABSENT"

def test_maxcount_revised_still_aligned():
    base, prop, path = _baseline()
    after = Graph()
    for t in base:
        after.add(t)
    after.remove((URIRef(prop), SH.maxCount, Literal(1)))
    after.add((URIRef(prop), SH.maxCount, Literal(2)))
    result = align_source_shape(
        base, after, prop, path, str(SH.MaxCountConstraintComponent)
    )
    assert result["shape_alignment"] == "ALIGNED"
    assert result.get("constraint_parameter_status") == "PRESENT"
