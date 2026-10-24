"""Structural fingerprints for SHACL-SPARQL constraints."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from shacl_compare.paths import is_absolute_iri

SPARQL_CONSTRAINT_COMPONENT = str(SH.SPARQLConstraintComponent)


def normalize_sparql_query(text: str) -> str:
    """Normalize SPARQL text for fingerprinting.

    Literals, IRI refs, and line comments are kept verbatim. Elsewhere,
    whitespace collapses to a single space. Keywords are not case-folded.
    """
    if not text:
        return ""
    n = len(text)
    out: list[str] = []
    i = 0
    pending_space = False

    def emit_space() -> None:
        nonlocal pending_space
        if out and not pending_space:
            pending_space = True

    def flush_space() -> None:
        nonlocal pending_space
        if pending_space:
            out.append(" ")
            pending_space = False

    def copy_span(start: int, end: int) -> int:
        flush_space()
        out.append(text[start:end])
        return end

    while i < n:
        ch = text[i]

        if text.startswith('"""', i) or text.startswith("'''", i):
            quote = text[i : i + 3]
            j = i + 3
            while j < n:
                if text.startswith(quote, j):
                    j += 3
                    break
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                j += 1
            i = copy_span(i, j)
            continue

        if ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                j += 1
            i = copy_span(i, j)
            continue

        if ch == "<":
            j = i + 1
            while j < n and text[j] != ">":
                j += 1
            if j < n:
                j += 1
            i = copy_span(i, j)
            continue

        if ch == "#":
            j = i + 1
            while j < n and text[j] not in "\r\n":
                j += 1
            if j < n and text[j] == "\r":
                j += 1
            if j < n and text[j] == "\n":
                j += 1
            i = copy_span(i, j)
            continue

        if ch.isspace():
            emit_space()
            i += 1
            continue

        flush_space()
        out.append(ch)
        i += 1

    return "".join(out).strip()


def _prefix_declarations(shapes: Graph, prefixes_node: Node) -> list[str]:
    decls: list[str] = []
    for decl in shapes.objects(prefixes_node, SH.declare):
        pref = list(shapes.objects(decl, SH.prefix))
        ns = list(shapes.objects(decl, SH.namespace))
        if len(pref) == 1 and len(ns) == 1:
            decls.append(f"{pref[0]}={ns[0]}")
    if list(shapes.objects(prefixes_node, RDF.first)):
        cur: Node | None = prefixes_node
        seen: set[Node] = set()
        while cur is not None and cur != RDF.nil and cur not in seen:
            seen.add(cur)
            first = list(shapes.objects(cur, RDF.first))
            if len(first) == 1:
                decl = first[0]
                pref = list(shapes.objects(decl, SH.prefix))
                ns = list(shapes.objects(decl, SH.namespace))
                if len(pref) == 1 and len(ns) == 1:
                    decls.append(f"{pref[0]}={ns[0]}")
            rest = list(shapes.objects(cur, RDF.rest))
            cur = rest[0] if len(rest) == 1 else None
    return sorted(set(decls))


def sparql_constraint_fingerprint(shapes: Graph, constraint: Node) -> str | None:
    selects = list(shapes.objects(constraint, SH.select))
    asks = list(shapes.objects(constraint, SH.ask))
    if len(selects) == 1 and not asks:
        kind = "select"
        qnode = selects[0]
    elif len(asks) == 1 and not selects:
        kind = "ask"
        qnode = asks[0]
    else:
        return None
    if not isinstance(qnode, Literal):
        return None
    query = normalize_sparql_query(str(qnode))
    if not query:
        return None

    prefix_parts: list[str] = []
    for pref_root in shapes.objects(constraint, SH.prefixes):
        prefix_parts.extend(_prefix_declarations(shapes, pref_root))
    prefix_parts = sorted(set(prefix_parts))
    prefix_s = ";".join(prefix_parts)

    deactivated = list(shapes.objects(constraint, SH.deactivated))
    deact = ""
    if len(deactivated) == 1 and isinstance(deactivated[0], Literal):
        deact = f"|deactivated:{str(deactivated[0]).lower()}"

    return f"SPARQL:{kind}:{query}|prefixes:{prefix_s}{deact}"


def _resolve_constraint_node(shapes: Graph, source_constraint: str) -> Node | None:
    if not source_constraint:
        return None
    if is_absolute_iri(source_constraint):
        node: Node = URIRef(source_constraint)
        if any(shapes.triples((node, None, None))):
            return node
        return None
    node = BNode(source_constraint)
    if any(shapes.triples((node, None, None))):
        return node
    return None


def fingerprint_from_source_constraint(
    shapes: Graph, source_constraint: str | None
) -> str | None:
    if not source_constraint:
        return None
    node = _resolve_constraint_node(shapes, str(source_constraint))
    if node is None:
        return None
    return sparql_constraint_fingerprint(shapes, node)


def shape_sparql_fingerprints(shapes: Graph, shape: Node) -> list[str]:
    fps: list[str] = []
    for c in shapes.objects(shape, SH.sparql):
        fp = sparql_constraint_fingerprint(shapes, c)
        if fp is not None:
            fps.append(fp)
    return sorted(fps)


def annotate_results_with_sparql_fingerprints(
    results: list[dict[str, Any]],
    shapes: Graph,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in results:
        r = dict(row)
        comp = str(r.get("source_constraint_component", "") or "")
        if comp != SPARQL_CONSTRAINT_COMPONENT:
            out.append(r)
            continue
        sc = r.get("source_constraint")
        fp = None
        if sc is not None:
            if isinstance(sc, list):
                # Ambiguous multi-valued sourceConstraint. Skip.
                fps = [
                    fingerprint_from_source_constraint(shapes, str(x)) for x in sc
                ]
                fps = [f for f in fps if f]
                fp = fps[0] if len(set(fps)) == 1 else None
            else:
                fp = fingerprint_from_source_constraint(shapes, str(sc))
        if fp is None:
            shape_s = str(r.get("source_shape", "") or "")
            if shape_s:
                if is_absolute_iri(shape_s):
                    shape_n: Node | None = URIRef(shape_s)
                else:
                    shape_n = BNode(shape_s)
                    if not any(shapes.triples((shape_n, None, None))):
                        shape_n = None
                if shape_n is not None and any(shapes.triples((shape_n, None, None))):
                    fps = shape_sparql_fingerprints(shapes, shape_n)
                    if len(fps) == 1:
                        fp = fps[0]
        if fp is not None:
            r["sparql_fingerprint"] = fp
        out.append(r)
    return out


def is_structural_constraint_fingerprint(fp: str | None) -> bool:
    if not fp:
        return False
    s = str(fp)
    return s.startswith("SPARQL:") or s.startswith("CUSTOMCC:")


def component_requires_structural_fingerprint(
    component: str,
    *,
    designated_fp: str | None = None,
) -> bool:
    if component == SPARQL_CONSTRAINT_COMPONENT:
        return True
    if designated_fp and str(designated_fp).startswith("CUSTOMCC:"):
        return True
    return False


def sparql_constraints_match(
    *,
    row_fp: str | None,
    designated_fp: str | None,
    component: str,
) -> bool:
    """Whether structural SPARQL / custom-CC identity allows a match.

    Ordinary Core components: always True.
    SPARQLConstraintComponent: designated fingerprint required and must equal row.
    Custom CC (CUSTOMCC: fingerprint): designated fingerprint required when set.
    During initial designation (designated_fp is None) CUSTOMCC rows may enter
    the candidate set so a unique fingerprint can be bound from the match.
    """
    if component == SPARQL_CONSTRAINT_COMPONENT:
        if designated_fp is None:
            return False
        return row_fp == designated_fp

    if designated_fp is not None and str(designated_fp).startswith("CUSTOMCC:"):
        return row_fp == designated_fp

    # Keep annotated CUSTOMCC rows during unbound selection.
    return True
