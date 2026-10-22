from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.targets import all_targets, membership_for_focus


EX = URIRef("http://example.org/ns#")


def _graphs():
    data = Graph()
    node = EX + "Node1"
    data.add((node, RDF.type, EX + "Person"))
    data.add((node, RDF.type, EX + "Agent"))
    data.add((node, EX + "firstName", Literal("a")))
    data.add((node, EX + "firstName", Literal("b")))

    shapes = Graph()
    person = EX + "PersonShape"
    prop = EX + "PersonShape-firstName"
    other = EX + "AgentShape"
    shapes.add((person, RDF.type, SH.NodeShape))
    shapes.add((person, SH.targetClass, EX + "Person"))
    shapes.add((person, SH.property, prop))
    shapes.add((prop, SH.path, EX + "firstName"))
    shapes.add((prop, SH.maxCount, Literal(1)))
    shapes.add((other, RDF.type, SH.NodeShape))
    shapes.add((other, SH.targetClass, EX + "Agent"))
    return data, shapes, str(node), str(prop)


def test_membership_ignores_unrelated_target_shape():
    data, shapes, focus, prop = _graphs()
    # Leave PersonShape (drop type Person) but remain Agent.
    data.remove((URIRef(focus), RDF.type, EX + "Person"))

    tables = all_targets(data, shapes, [])
    memb = membership_for_focus(tables, focus, prop, shapes)
    assert memb["targeted"] is False
    assert memb["status"] == "LOST_OR_NOT_IN_OWNER"
    assert str(EX + "AgentShape") not in memb.get("owner_shapes", [])


def test_membership_retained_only_for_owner_shape():
    data, shapes, focus, prop = _graphs()
    tables = all_targets(data, shapes, [])
    memb = membership_for_focus(tables, focus, prop, shapes)
    assert memb["targeted"] is True
    assert str(EX + "PersonShape") in memb["owner_shapes"]
