from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, SH
from rdflib.term import Node

from shacl_compare.terms import node_focus_key


def shacl_instances(data: Graph, class_node: Node) -> set[Node]:
    """SHACL instances of class_node (rdf:type / rdfs:subClassOf*)."""
    subclasses: set[Node] = {class_node}
    changed = True
    while changed:
        changed = False
        for sub, _, parent in data.triples((None, RDFS.subClassOf, None)):
            if parent in subclasses and sub not in subclasses:
                subclasses.add(sub)
                changed = True
    instances: set[Node] = set()
    for cls in subclasses:
        instances.update(data.subjects(RDF.type, cls))
    return instances


def node_shapes(shapes: Graph) -> list[Node]:
    found = set(shapes.subjects(RDF.type, SH.NodeShape))
    for pred in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf):
        found.update(shapes.subjects(pred, None))
    return sorted(found, key=str)


def find_owner_node_shapes(shapes: Graph, property_shape: str | Node) -> list[Node]:
    from shacl_compare.designate import resolve_shape_node

    if isinstance(property_shape, Node):
        ps: Node | None = property_shape
    else:
        ps = resolve_shape_node(shapes, property_shape)
    if ps is None:
        return []
    return sorted(shapes.subjects(SH.property, ps), key=str)


def _is_shape(shapes: Graph, shape: Node) -> bool:
    return (shape, RDF.type, SH.NodeShape) in shapes or (
        shape,
        RDF.type,
        SH.PropertyShape,
    ) in shapes


def _is_rdfs_class(shapes: Graph, shape: Node) -> bool:
    return (shape, RDF.type, RDFS.Class) in shapes


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
        for node in shacl_instances(data, cls):
            add(node, f"targetClass:{cls}")

    if _is_shape(shapes, shape) and _is_rdfs_class(shapes, shape):
        for node in shacl_instances(data, shape):
            add(node, f"implicitClassTarget:{shape}")

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
    shapes: Graph | None = None,
) -> dict[str, Any]:
    if not source_shape or shapes is None:
        return {
            "targeted": False,
            "owner_shapes": [],
            "status": "NOT_EVALUATED",
            "reason": "missing_source_shape_or_shapes_graph",
        }

    from shacl_compare.designate import resolve_shape_node

    owners = find_owner_node_shapes(shapes, source_shape)
    if not owners:
        # Standalone property shapes act as their own owner.
        resolved = resolve_shape_node(shapes, source_shape)
        if resolved is not None and any(
            True for _ in shapes.predicate_objects(resolved)
        ):
            owners = [resolved]
        else:
            return {
                "targeted": False,
                "owner_shapes": [],
                "status": "NOT_EVALUATED",
                "reason": "no_owner_node_shape_for_property_shape",
            }

    owner_iris = {str(o) for o in owners}
    matching_owners = [
        table["shape"]
        for table in target_tables
        if table["shape"] in owner_iris and focus_key in table["members"]
    ]
    if matching_owners:
        return {
            "targeted": True,
            "owner_shapes": sorted(set(matching_owners)),
            "status": "IN_OWNER",
        }
    return {
        "targeted": False,
        "owner_shapes": sorted(owner_iris),
        "status": "LOST_OR_NOT_IN_OWNER",
    }
