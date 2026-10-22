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
    return sorted(shapes.subjects(SH.property, property_shape), key=str)


def _component_parameter(component: str) -> URIRef | None:
    if component.endswith("MinCountConstraintComponent") or component == str(
        SH.MinCountConstraintComponent
    ):
        return SH.minCount
    if component.endswith("MaxCountConstraintComponent") or component == str(
        SH.MaxCountConstraintComponent
    ):
        return SH.maxCount
    return None


def _shape_has_path(shapes: Graph, shape: Node, path: str) -> bool:
    return path in {str(p) for p in shapes.objects(shape, SH.path)}


def _parents_link(shapes: Graph, parent: Node, prop: Node) -> bool:
    return (parent, SH.property, prop) in shapes


def align_source_shape(
    shapes_baseline: Graph,
    shapes_after: Graph,
    source_shape: str,
    path: str,
    component: str,
) -> dict[str, Any]:
    shape_uri = URIRef(source_shape)
    param = _component_parameter(component)
    baseline_parents = find_parent_node_shapes(shapes_baseline, shape_uri)

    subject_defined = any(shapes_after.triples((shape_uri, None, None)))
    if subject_defined:
        if not _shape_has_path(shapes_after, shape_uri, path):
            return {
                "shape_alignment": "UNRESOLVED",
                "aligned_source_shape": None,
                "reason": "same_iri_present_but_path_mismatch_or_missing",
            }
        if baseline_parents:
            linked = [
                p
                for p in baseline_parents
                if any(shapes_after.triples((p, None, None)))
                and _parents_link(shapes_after, p, shape_uri)
            ]
            if not linked:
                return {
                    "shape_alignment": "UNRESOLVED",
                    "aligned_source_shape": None,
                    "reason": "same_iri_present_but_parent_property_link_missing",
                }
        param_status = "NOT_APPLICABLE"
        if param is not None:
            vals = list(shapes_after.objects(shape_uri, param))
            param_status = "PRESENT" if vals else "ABSENT"
        return {
            "shape_alignment": "ALIGNED",
            "aligned_source_shape": source_shape,
            "reason": "same_iri_with_matching_path_and_parent_context",
            "constraint_parameter_status": param_status,
        }

    if not baseline_parents:
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "baseline_source_shape_iri_absent_and_no_parent_node_shape",
        }

    candidates: list[str] = []
    for parent in baseline_parents:
        if not any(shapes_after.triples((parent, None, None))):
            continue
        for ps in shapes_after.objects(parent, SH.property):
            if _shape_has_path(shapes_after, ps, path):
                candidates.append(str(ps))

    unique = sorted(set(candidates))
    if len(unique) == 1:
        aligned = URIRef(unique[0])
        param_status = "NOT_APPLICABLE"
        if param is not None:
            vals = list(shapes_after.objects(aligned, param))
            param_status = "PRESENT" if vals else "ABSENT"
        return {
            "shape_alignment": "ALIGNED",
            "aligned_source_shape": unique[0],
            "reason": "unique_parent_path_fingerprint",
            "constraint_parameter_status": param_status,
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
    if focus_key.startswith("bnode["):
        return [], "blank_focus_key_unmatched"
    return [], "focus_key"


def original_cardinality_parameter(
    shapes: Graph,
    source_shape: str,
    component: str,
) -> tuple[URIRef, list[str]] | None:
    shape = URIRef(source_shape)
    param = _component_parameter(component)
    if param is None:
        return None
    vals = sorted(str(v) for v in shapes.objects(shape, param))
    return param, vals


def _resolve_focus(
    data: Graph,
    focus_key: str,
    focus_key_properties: list[URIRef],
) -> tuple[Node | None, str | None]:
    if not focus_key.startswith("bnode["):
        return URIRef(focus_key), None
    hits = [
        s
        for s in set(data.subjects())
        if node_focus_key(data, s, focus_key_properties) == focus_key
    ]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) == 0:
        return None, "focus_node_not_found_in_data"
    return None, "ambiguous_focus_key_multiple_nodes"


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

    focus_node, resolve_reason = _resolve_focus(data, focus_key, focus_key_properties)
    if focus_node is None:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": resolve_reason or "focus_node_not_found_in_data",
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
