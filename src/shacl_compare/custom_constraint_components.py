"""Fingerprints for user-defined SPARQL-based constraint components."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from shacl_compare.paths import is_absolute_iri
from shacl_compare.sparql_constraints import normalize_sparql_query

SHACL_NS = str(SH)
CUSTOM_CC_PREFIX = "CUSTOMCC:"


def is_user_constraint_component(shapes: Graph, component: str) -> bool:
    if not component or not is_absolute_iri(component):
        return False
    if component.startswith(SHACL_NS):
        return False
    node = URIRef(component)
    return (node, RDF.type, SH.ConstraintComponent) in shapes


def is_custom_cc_fingerprint(fp: str | None) -> bool:
    return bool(fp) and str(fp).startswith(CUSTOM_CC_PREFIX)


def _resolve_shape(shapes: Graph, source_shape: str) -> Node | None:
    if is_absolute_iri(source_shape):
        node: Node = URIRef(source_shape)
        if any(shapes.triples((node, None, None))):
            return node
        return None
    node = BNode(source_shape)
    if any(shapes.triples((node, None, None))):
        return node
    return None


def _parameter_paths(shapes: Graph, component: Node) -> list[URIRef] | None:
    paths: list[URIRef] = []
    for param in shapes.objects(component, SH.parameter):
        path_vals = list(shapes.objects(param, SH.path))
        if len(path_vals) != 1:
            return None
        path = path_vals[0]
        if not isinstance(path, URIRef):
            # Blank/complex parameter paths are not fingerprintable.
            return None
        paths.append(path)
    if not paths:
        return None
    return sorted(paths, key=str)


def _binding_token(value: Node) -> str | None:
    if isinstance(value, URIRef):
        return f"<{value}>"
    if isinstance(value, Literal):
        if value.language:
            return f'"{value}"@{value.language}'
        if value.datatype:
            return f'"{value}"^^<{value.datatype}>'
        return f'"{value}"'
    # Blank parameter values are unstable across parses.
    return None


def _parameter_bindings(
    shapes: Graph, shape: Node, param_paths: list[URIRef]
) -> str | None:
    parts: list[str] = []
    for path in param_paths:
        vals = list(shapes.objects(shape, path))
        if not vals:
            # Absent optional parameters are recorded explicitly.
            parts.append(f"{path}=∅")
            continue
        tokens: list[str] = []
        for v in vals:
            tok = _binding_token(v)
            if tok is None:
                return None
            tokens.append(tok)
        parts.append(f"{path}=" + ",".join(sorted(tokens)))
    return ";".join(parts)


def _shape_is_property_shape(shapes: Graph, shape: Node) -> bool:
    if list(shapes.objects(shape, SH.path)):
        return True
    return (shape, RDF.type, SH.PropertyShape) in shapes


def _validator_query(
    shapes: Graph, component: Node, shape: Node
) -> tuple[str, str, str] | None:
    """Return (slot, kind, normalized_query) for the validator pySHACL would use.

    Mirrors pySHACL 0.40.x selection rules:
    - property shape + sh:propertyValidator → SELECT
    - node shape + sh:nodeValidator → SELECT
    - else sh:validator → ASK
    """
    prop_vals = list(shapes.objects(component, SH.propertyValidator))
    node_vals = list(shapes.objects(component, SH.nodeValidator))
    gen_vals = list(shapes.objects(component, SH.validator))

    if _shape_is_property_shape(shapes, shape) and prop_vals:
        if len(prop_vals) != 1:
            return None
        slot, vnode = "propertyValidator", prop_vals[0]
        expect_kind = "select"
    elif (not _shape_is_property_shape(shapes, shape)) and node_vals:
        if len(node_vals) != 1:
            return None
        slot, vnode = "nodeValidator", node_vals[0]
        expect_kind = "select"
    elif gen_vals:
        if len(gen_vals) != 1:
            return None
        slot, vnode = "validator", gen_vals[0]
        expect_kind = "ask"
    else:
        return None

    selects = list(shapes.objects(vnode, SH.select))
    asks = list(shapes.objects(vnode, SH.ask))
    if len(selects) == 1 and not asks:
        kind = "select"
        qnode = selects[0]
    elif len(asks) == 1 and not selects:
        kind = "ask"
        qnode = asks[0]
    else:
        return None
    if kind != expect_kind:
        # Validator kind does not match the pySHACL slot.
        return None
    if not isinstance(qnode, Literal):
        return None
    query = normalize_sparql_query(str(qnode))
    if not query:
        return None
    return slot, kind, query


def custom_cc_fingerprint(
    shapes: Graph,
    component: str,
    source_shape: str,
) -> str | None:
    if not is_user_constraint_component(shapes, component):
        return None
    comp_node = URIRef(component)
    shape = _resolve_shape(shapes, source_shape)
    if shape is None:
        return None
    param_paths = _parameter_paths(shapes, comp_node)
    if param_paths is None:
        return None
    bindings = _parameter_bindings(shapes, shape, param_paths)
    if bindings is None:
        return None
    validator = _validator_query(shapes, comp_node, shape)
    if validator is None:
        return None
    slot, kind, query = validator
    return (
        f"{CUSTOM_CC_PREFIX}{component}|params:{bindings}"
        f"|slot:{slot}|{kind}:{query}"
    )


def annotate_results_with_custom_cc_fingerprints(
    results: list[dict[str, Any]],
    shapes: Graph,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in results:
        r = dict(row)
        if r.get("sparql_fingerprint"):
            out.append(r)
            continue
        comp = str(r.get("source_constraint_component", "") or "")
        if not is_user_constraint_component(shapes, comp):
            out.append(r)
            continue
        shape_s = str(r.get("source_shape", "") or "")
        if not shape_s:
            out.append(r)
            continue
        fp = custom_cc_fingerprint(shapes, comp, shape_s)
        if fp is not None:
            r["sparql_fingerprint"] = fp
        out.append(r)
    return out
