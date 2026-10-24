"""Structural fingerprints for SHACL property paths."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node


class PathFingerprintError(ValueError):
    pass


def is_absolute_iri(value: str) -> bool:
    return value.startswith(("http://", "https://", "urn:"))


def _resolve_shape_node(shapes: Graph, source_shape: str) -> Node | None:
    if is_absolute_iri(source_shape):
        node: Node = URIRef(source_shape)
        if any(shapes.triples((node, None, None))):
            return node
        return None
    node = BNode(source_shape)
    if any(shapes.triples((node, None, None))):
        return node
    return None


def _rdf_list(graph: Graph, head: Node) -> list[Node] | None:
    items: list[Node] = []
    seen: set[Node] = set()
    cur: Node | None = head
    while cur is not None and cur != RDF.nil:
        if cur in seen:
            return None
        seen.add(cur)
        first = list(graph.objects(cur, RDF.first))
        if len(first) != 1:
            return None
        items.append(first[0])
        rest = list(graph.objects(cur, RDF.rest))
        if len(rest) != 1:
            return None
        cur = rest[0]
    return items


def path_node_fingerprint(graph: Graph, path_node: Node, *, _depth: int = 0) -> str:
    if _depth > 64:
        raise PathFingerprintError("path nesting too deep")

    if isinstance(path_node, URIRef):
        return f"P:<{path_node}>"

    if isinstance(path_node, Literal):
        raise PathFingerprintError("literal cannot be a SHACL path")

    inv = list(graph.objects(path_node, SH.inversePath))
    if len(inv) == 1 and not list(graph.objects(path_node, SH.alternativePath)):
        if list(graph.objects(path_node, RDF.first)):
            pass
        else:
            return f"I({path_node_fingerprint(graph, inv[0], _depth=_depth + 1)})"

    alt = list(graph.objects(path_node, SH.alternativePath))
    if len(alt) == 1:
        members = _rdf_list(graph, alt[0])
        if members is None:
            raise PathFingerprintError("malformed sh:alternativePath list")
        fps = sorted(
            path_node_fingerprint(graph, m, _depth=_depth + 1) for m in members
        )
        return "A(" + "|".join(fps) + ")"

    for pred, tag in (
        (SH.zeroOrMorePath, "Z*"),
        (SH.oneOrMorePath, "O+"),
        (SH.zeroOrOnePath, "Z?"),
    ):
        vals = list(graph.objects(path_node, pred))
        if len(vals) == 1:
            return (
                f"{tag}({path_node_fingerprint(graph, vals[0], _depth=_depth + 1)})"
            )

    if list(graph.objects(path_node, RDF.first)):
        members = _rdf_list(graph, path_node)
        if members is None:
            raise PathFingerprintError("malformed sequence path list")
        fps = [path_node_fingerprint(graph, m, _depth=_depth + 1) for m in members]
        return "S(" + ",".join(fps) + ")"

    if inv:
        raise PathFingerprintError("malformed sh:inversePath node")

    raise PathFingerprintError(f"unrecognized SHACL path node {path_node!r}")


def shape_path_fingerprint(shapes: Graph, shape: Node) -> str | None:
    paths = list(shapes.objects(shape, SH.path))
    if not paths:
        return ""
    if len(paths) != 1:
        return None
    try:
        return path_node_fingerprint(shapes, paths[0])
    except PathFingerprintError:
        return None


def shape_path_fingerprint_str(shapes: Graph, source_shape: str) -> str | None:
    node = _resolve_shape_node(shapes, source_shape)
    if node is None:
        return None
    return shape_path_fingerprint(shapes, node)


def predicate_path_fingerprint(iri: str) -> str:
    return f"P:<{iri}>"


def annotate_results_with_path_fingerprints(
    results: list[dict[str, Any]],
    shapes: Graph,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in results:
        r = dict(row)
        shape_s = str(r.get("source_shape", "") or "")
        fp = shape_path_fingerprint_str(shapes, shape_s) if shape_s else None
        if fp is not None:
            r["path_fingerprint"] = fp
        else:
            rp = str(r.get("result_path", "") or "")
            if is_absolute_iri(rp):
                r["path_fingerprint"] = predicate_path_fingerprint(rp)
            elif rp == "":
                r["path_fingerprint"] = ""
        out.append(r)
    return out


def paths_match(
    *,
    row_path: str,
    row_fp: str | None,
    designated_path: str,
    designated_fp: str | None,
) -> bool:
    if designated_path == "" and (row_path == "" or row_fp == ""):
        if designated_fp in (None, "") and row_fp in (None, ""):
            return row_path == ""
        return (row_fp or "") == (designated_fp or "")

    if is_absolute_iri(designated_path) and is_absolute_iri(row_path):
        return row_path == designated_path

    if designated_fp and row_fp:
        return designated_fp == row_fp

    return row_path == designated_path


def resolve_designation_path_fingerprint(
    shapes: Graph,
    *,
    path: str,
    source_shape: str | None,
) -> str | None:
    """Fingerprint for a CLI path argument.

    Absolute IRIs are PredicatePaths. Empty path uses source_shape sh:path when
    available. Non-IRI text needs a fingerprint from ValidationResults or shape.
    """
    if is_absolute_iri(path):
        return predicate_path_fingerprint(path)
    if source_shape:
        fp = shape_path_fingerprint_str(shapes, source_shape)
        if fp is not None:
            return fp
    if path == "":
        return ""
    node: Node = BNode(path)
    if any(shapes.objects(None, SH.path)) and (
        any(True for _ in shapes.triples((None, SH.path, node)))
        or any(shapes.triples((node, None, None)))
    ):
        try:
            return path_node_fingerprint(shapes, node)
        except PathFingerprintError:
            return None
    return None
