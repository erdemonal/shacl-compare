from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SH

from shacl_compare.targets import all_targets, membership_for_focus, shacl_instances


EX = URIRef("http://example.org/implicit#")


def test_shacl_instances_direct_and_subclass():
    data = Graph()
    data.add((EX + "Alice", RDF.type, EX + "Person"))
    data.add((EX + "Bob", RDF.type, EX + "Student"))
    data.add((EX + "Student", RDFS.subClassOf, EX + "Person"))
    data.add((EX + "Carol", RDF.type, EX + "Place"))

    got = {str(n) for n in shacl_instances(data, EX + "Person")}
    assert str(EX + "Alice") in got
    assert str(EX + "Bob") in got
    assert str(EX + "Carol") not in got


def test_implicit_class_target_direct():
    data = Graph()
    data.add((EX + "Alice", RDF.type, EX + "Person"))
    data.add((EX + "Alice", EX + "name", Literal("a")))

    shapes = Graph()
    person = EX + "Person"
    prop = EX + "Person-name"
    shapes.add((person, RDF.type, RDFS.Class))
    shapes.add((person, RDF.type, SH.NodeShape))
    shapes.add((person, SH.property, prop))
    shapes.add((prop, RDF.type, SH.PropertyShape))
    shapes.add((prop, SH.path, EX + "name"))
    shapes.add((prop, SH.maxCount, Literal(1)))

    tables = all_targets(data, shapes, [])
    memb = membership_for_focus(tables, str(EX + "Alice"), str(prop), shapes)
    assert memb["targeted"] is True
    assert memb["status"] == "IN_OWNER"
    person_table = next(t for t in tables if t["shape"] == str(person))
    assert any(
        r.startswith("implicitClassTarget:")
        for r in person_table["membership_reasons"][str(EX + "Alice")]
    )


def test_implicit_class_target_via_subclass():
    data = Graph()
    data.add((EX + "Alice", RDF.type, EX + "Student"))
    data.add((EX + "Student", RDFS.subClassOf, EX + "Person"))
    data.add((EX + "Alice", EX + "name", Literal("a")))

    shapes = Graph()
    person = EX + "Person"
    prop = EX + "Person-name"
    shapes.add((person, RDF.type, RDFS.Class))
    shapes.add((person, RDF.type, SH.NodeShape))
    shapes.add((person, SH.property, prop))
    shapes.add((prop, RDF.type, SH.PropertyShape))
    shapes.add((prop, SH.path, EX + "name"))
    shapes.add((prop, SH.maxCount, Literal(1)))

    tables = all_targets(data, shapes, [])
    memb = membership_for_focus(tables, str(EX + "Alice"), str(prop), shapes)
    assert memb["targeted"] is True
    assert memb["status"] == "IN_OWNER"


def test_explicit_target_class_via_subclass():
    data = Graph()
    data.add((EX + "Alice", RDF.type, EX + "Student"))
    data.add((EX + "Student", RDFS.subClassOf, EX + "Person"))
    data.add((EX + "Alice", EX + "name", Literal("a")))

    shapes = Graph()
    shape = EX + "PersonShape"
    prop = EX + "PersonShape-name"
    shapes.add((shape, RDF.type, SH.NodeShape))
    shapes.add((shape, SH.targetClass, EX + "Person"))
    shapes.add((shape, SH.property, prop))
    shapes.add((prop, RDF.type, SH.PropertyShape))
    shapes.add((prop, SH.path, EX + "name"))
    shapes.add((prop, SH.maxCount, Literal(1)))

    tables = all_targets(data, shapes, [])
    memb = membership_for_focus(tables, str(EX + "Alice"), str(prop), shapes)
    assert memb["targeted"] is True
    assert memb["status"] == "IN_OWNER"
    shape_table = next(t for t in tables if t["shape"] == str(shape))
    assert any(
        r.startswith("targetClass:")
        for r in shape_table["membership_reasons"][str(EX + "Alice")]
    )
