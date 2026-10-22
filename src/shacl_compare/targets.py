from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from shacl_compare.terms import node_focus_key


def node_shapes(shapes: Graph) -> list[Node]:
    found = set(shapes.subjects(RDF.type, SH.NodeShape))
    # Also treat subjects of target predicates as node shapes.
    for pred in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf):
        found.update(shapes.subjects(pred, None))
    return sorted(found, key=str)


def targets_for_shape(
    data: Graph,
    shapes: Graph,
    shape: Node,
    focus_key_properties: list[URIRef],
) -> dict[str, Any]:
    members: dict[str, list[str]] = {}

    def add(node: Node, reason: str) -> None:
        key = node_focus_key(data, node, focus_key_properties)
        members.setdefault(key, []).append(reason)

    for cls in shapes.objects(shape, SH.targetClass):
        for node in data.subjects(RDF.type, cls):
            add(node, f"targetClass:{cls}")

    for node in shapes.objects(shape, SH.targetNode):
        add(node, f"targetNode:{node}")

    for pred in shapes.objects(shape, SH.targetSubjectsOf):
        for node in data.subjects(pred, None):
            add(node, f"targetSubjectsOf:{pred}")

    for pred in shapes.objects(shape, SH.targetObjectsOf):
        for node in data.objects(None, pred):
            add(node, f"targetObjectsOf:{pred}")

    return {
        "shape": str(shape),
        "members": sorted(members),
        "membership_reasons": {k: sorted(set(v)) for k, v in sorted(members.items())},
    }


def all_targets(
    data: Graph,
    shapes: Graph,
    focus_key_properties: list[URIRef],
) -> list[dict[str, Any]]:
    return [
        targets_for_shape(data, shapes, shape, focus_key_properties)
        for shape in node_shapes(shapes)
    ]


def membership_for_focus(
    target_tables: list[dict[str, Any]],
    focus_key: str,
    source_shape: str | None,
) -> dict[str, Any]:
    """Return whether focus_key is targeted, preferring the source shape's parent when known."""
    # source_shape in ValidationResult is often a property shape; membership is on node shapes.
    matching = []
    for table in target_tables:
        if focus_key in table["members"]:
            matching.append(table["shape"])

    if not matching:
        return {"targeted": False, "shapes": []}

    return {"targeted": True, "shapes": sorted(set(matching))}
