from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import SH
from rdflib.term import Node

from shacl_compare.terms import node_focus_key


class DesignateError(ValueError):
    pass


def result_matches(
    row: dict[str, Any],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
) -> bool:
    return (
        row.get("focus_key") == focus_key
        and str(row.get("result_path", "")) == path
        and str(row.get("source_shape", "")) == source_shape
        and str(row.get("source_constraint_component", "")) == component
        and str(row.get("severity", "")) == severity
    )


def select_designated(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
) -> dict[str, Any]:
    matches = [
        r
        for r in results
        if result_matches(
            r,
            focus_key=focus_key,
            path=path,
            source_shape=source_shape,
            component=component,
            severity=severity,
        )
    ]
    if len(matches) == 0:
        raise DesignateError(
            "designated baseline failure matched 0 ValidationResults"
        )
    if len(matches) > 1:
        raise DesignateError(
            f"designated baseline failure matched {len(matches)} ValidationResults"
        )
    return matches[0]


def find_parent_node_shapes(shapes: Graph, property_shape: Node) -> list[Node]:
    parents = list(shapes.subjects(SH.property, property_shape))
    return sorted(parents, key=str)


def align_source_shape(
    shapes_baseline: Graph,
    shapes_after: Graph,
    source_shape: str,
    path: str,
    component: str,
) -> dict[str, Any]:
    """Align baseline source_shape to a shape in shapes_after."""
    shape_uri = URIRef(source_shape)
    present = any(shapes_after.triples((shape_uri, None, None))) or any(
        shapes_after.triples((None, None, shape_uri))
    )
    if present:
        return {
            "shape_alignment": "ALIGNED",
            "aligned_source_shape": source_shape,
            "reason": "same_iri_present_in_revised_shapes",
        }

    baseline_node = URIRef(source_shape)
    parents = find_parent_node_shapes(shapes_baseline, baseline_node)
    if not parents:
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "baseline_source_shape_iri_absent_and_no_parent_node_shape",
        }

    candidates: list[str] = []
    for parent in parents:
        parent_iri = str(parent)
        # Candidate property shapes under same parent IRI with same path.
        after_parents = (
            [URIRef(parent_iri)]
            if any(True for _ in shapes_after.predicate_objects(URIRef(parent_iri)))
            else []
        )
        for ap in after_parents:
            for ps in shapes_after.objects(ap, SH.property):
                paths = {str(p) for p in shapes_after.objects(ps, SH.path)}
                if path in paths:
                    candidates.append(str(ps))

    unique = sorted(set(candidates))
    if len(unique) == 1:
        return {
            "shape_alignment": "ALIGNED",
            "aligned_source_shape": unique[0],
            "reason": "unique_parent_path_fingerprint",
        }
    if len(unique) == 0:
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "no_structural_candidate_for_source_shape",
        }
    return {
        "shape_alignment": "UNRESOLVED",
        "aligned_source_shape": None,
        "reason": "multiple_structural_candidates_for_source_shape",
        "candidates": unique,
    }


def match_designated_after(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
) -> tuple[list[dict[str, Any]], str]:
    """Return (matches, match_mode).

    For blank focus keys, if the content key drifted (repair changed key
    properties), fall back to a unique (path, source_shape, component, severity)
    match among blank-keyed results. Multiple candidates → empty + ambiguous mode.
    """
    direct = [
        r
        for r in results
        if result_matches(
            r,
            focus_key=focus_key,
            path=path,
            source_shape=source_shape,
            component=component,
            severity=severity,
        )
    ]
    if direct:
        return direct, "focus_key"
    if not focus_key.startswith("bnode["):
        return [], "focus_key"
    soft = [
        r
        for r in results
        if str(r.get("focus_key", "")).startswith("bnode[")
        and str(r.get("result_path", "")) == path
        and str(r.get("source_shape", "")) == source_shape
        and str(r.get("source_constraint_component", "")) == component
        and str(r.get("severity", "")) == severity
    ]
    if len(soft) == 1:
        return soft, "blank_focus_unique_component_path"
    if len(soft) > 1:
        return [], "blank_focus_ambiguous"
    return [], "focus_key"


def original_cardinality_parameter(
    shapes: Graph,
    source_shape: str,
    component: str,
) -> tuple[URIRef, list[str]] | None:
    shape = URIRef(source_shape)
    if component.endswith("MinCountConstraintComponent"):
        vals = sorted(str(v) for v in shapes.objects(shape, SH.minCount))
        return SH.minCount, vals
    if component.endswith("MaxCountConstraintComponent"):
        vals = sorted(str(v) for v in shapes.objects(shape, SH.maxCount))
        return SH.maxCount, vals
    return None


def evaluate_original_cardinality_on_focus(
    data: Graph,
    shapes_baseline: Graph,
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    focus_key_properties: list[URIRef],
    targeted: bool,
) -> dict[str, Any]:
    """Evaluate original minCount/maxCount on focus against baseline shapes encoding."""
    if not targeted:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "focus_not_targeted",
        }

    param = original_cardinality_parameter(shapes_baseline, source_shape, component)
    if param is None:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "unsupported_component_for_original_evaluation",
        }

    parameter, values = param
    if len(values) != 1:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "baseline_parameter_not_unique",
            "parameter": str(parameter),
            "values": values,
        }

    # Resolve focus node in data by key.
    focus_node = _resolve_focus(data, focus_key, focus_key_properties)
    if focus_node is None:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "focus_node_not_found_in_data",
        }

    count = len(list(data.objects(focus_node, URIRef(path))))
    expected = int(values[0])
    if parameter == SH.minCount:
        ok = count >= expected
    else:
        ok = count <= expected

    return {
        "original_constraint_evaluation": "SATISFIED" if ok else "VIOLATED",
        "parameter": str(parameter),
        "expected": expected,
        "observed_value_count": count,
    }


def _resolve_focus(
    data: Graph,
    focus_key: str,
    focus_key_properties: list[URIRef],
) -> Node | None:
    if not focus_key.startswith("bnode["):
        return URIRef(focus_key)
    for s in set(data.subjects()):
        if node_focus_key(data, s, focus_key_properties) == focus_key:
            return s
    return None
