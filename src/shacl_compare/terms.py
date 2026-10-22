from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
from rdflib.term import Node


def term_key(term: Node) -> tuple[Any, ...]:
    if isinstance(term, Literal):
        return (
            "L",
            str(term),
            str(term.datatype) if term.datatype else None,
            term.language,
        )
    if isinstance(term, URIRef):
        return ("U", str(term))
    if isinstance(term, BNode):
        return ("B", str(term))
    return ("N", str(term), type(term).__name__)


def triple_key(triple: tuple[Node, Node, Node]) -> tuple[Any, ...]:
    return tuple(term_key(t) for t in triple)


def serialize_term(term: Node) -> str:
    return str(term)


def serialize_triple(triple: tuple[Node, Node, Node]) -> dict[str, str]:
    s, p, o = triple
    return {
        "subject": serialize_term(s),
        "predicate": serialize_term(p),
        "object": serialize_term(o),
    }


def focus_content_key(graph: Graph, node: Node, key_properties: list[URIRef]) -> str:
    parts: list[str] = []
    types = sorted(str(t) for t in graph.objects(node, RDF.type))
    if types:
        parts.append("type=" + ",".join(types))
    for prop in key_properties:
        vals = sorted(serialize_term(o) for o in graph.objects(node, prop))
        parts.append(f"{prop}=" + ",".join(vals))
    return "bnode[" + "|".join(parts) + "]"


def node_focus_key(graph: Graph, node: Node, key_properties: list[URIRef]) -> str:
    if isinstance(node, BNode):
        return focus_content_key(graph, node, key_properties)
    return str(node)
