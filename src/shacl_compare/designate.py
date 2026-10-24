from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import SH
from rdflib.term import Node

from shacl_compare.paths import (
    is_absolute_iri,
    paths_match,
    shape_path_fingerprint,
)
from shacl_compare.sparql_constraints import (
    SPARQL_CONSTRAINT_COMPONENT,
    component_requires_structural_fingerprint,
    is_structural_constraint_fingerprint,
    sparql_constraints_match,
)
from shacl_compare.terms import node_focus_key


class DesignateError(ValueError):
    pass


def resolve_shape_node(shapes: Graph, source_shape: str) -> Node | None:
    """Resolve a source-shape string to a node in *shapes*.

    Absolute IRIs resolve as URIRef. Blank ids are process-local only.
    """
    if is_absolute_iri(source_shape):
        node: Node = URIRef(source_shape)
        if any(shapes.triples((node, None, None))):
            return node
        return None
    node = BNode(source_shape)
    if any(shapes.triples((node, None, None))):
        return node
    return None


def result_matches_core(
    row: dict[str, Any],
    *,
    focus_key: str,
    path: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> bool:
    if row.get("focus_key") != focus_key:
        return False
    if str(row.get("source_constraint_component", "")) != component:
        return False
    if str(row.get("severity", "")) != severity:
        return False
    if not paths_match(
        row_path=str(row.get("result_path", "") or ""),
        row_fp=row.get("path_fingerprint"),
        designated_path=path,
        designated_fp=path_fingerprint,
    ):
        return False
    return sparql_constraints_match(
        row_fp=row.get("sparql_fingerprint"),
        designated_fp=sparql_fingerprint,
        component=component,
    )


def result_matches(
    row: dict[str, Any],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> bool:
    return result_matches_core(
        row,
        focus_key=focus_key,
        path=path,
        component=component,
        severity=severity,
        path_fingerprint=path_fingerprint,
        sparql_fingerprint=sparql_fingerprint,
    ) and str(row.get("source_shape", "")) == source_shape


def _sorted_core_matches(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    matches = [
        r
        for r in results
        if result_matches_core(
            r,
            focus_key=focus_key,
            path=path,
            component=component,
            severity=severity,
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        )
    ]
    return sorted(
        matches,
        key=lambda r: (
            str(r.get("source_shape", "")),
            str(r.get("value", "")),
            str(r.get("message", "")),
        ),
    )


def _format_candidates(matches: list[dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(matches, start=1):
        lines.append(
            f"  [{i}] source_shape={r.get('source_shape')!r} "
            f"value={r.get('value')!r} message={r.get('message')!r}"
        )
    return "\n".join(lines)


def _sort_key_result(r: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(r.get("sparql_fingerprint", "")),
        str(r.get("source_shape", "")),
        str(r.get("value", "")),
        str(r.get("message", "")),
        str(r.get("source_constraint", "")),
    )


def select_designated(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    component: str,
    severity: str,
    source_shape: str | None = None,
    designation_index: int | None = None,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Select one baseline ValidationResult.

    Absolute IRI source shapes join the match key. Otherwise match on focus,
    path, component, and severity. path_fingerprint and sparql_fingerprint
    disambiguate complex paths and SPARQL constraints. designation_index is
    required when several candidates remain.
    """
    use_iri = bool(source_shape) and is_absolute_iri(source_shape)
    mode = "iri_source_shape" if use_iri else "core_signature"
    is_sparql = component == SPARQL_CONSTRAINT_COMPONENT
    is_structural_sparql_family = is_sparql or any(
        is_structural_constraint_fingerprint(r.get("sparql_fingerprint"))
        and str(r.get("source_constraint_component", "")) == component
        for r in results
    )

    if use_iri:
        assert source_shape is not None
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
                path_fingerprint=path_fingerprint,
                sparql_fingerprint=sparql_fingerprint,
            )
        ]
        matches = sorted(matches, key=_sort_key_result)
    else:
        matches = _sorted_core_matches(
            results,
            focus_key=focus_key,
            path=path,
            component=component,
            severity=severity,
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        )
        matches = sorted(matches, key=_sort_key_result)

    if len(matches) == 0 and is_structural_sparql_family and sparql_fingerprint is None:
        def _sparql_loose(r: dict[str, Any]) -> bool:
            if r.get("focus_key") != focus_key:
                return False
            if str(r.get("source_constraint_component", "")) != component:
                return False
            if str(r.get("severity", "")) != severity:
                return False
            if use_iri and source_shape is not None:
                if str(r.get("source_shape", "")) != source_shape:
                    return False
            if path not in ("",) and is_absolute_iri(path):
                if not paths_match(
                    row_path=str(r.get("result_path", "") or ""),
                    row_fp=r.get("path_fingerprint"),
                    designated_path=path,
                    designated_fp=path_fingerprint,
                ):
                    return False
            return True

        relaxed = sorted(
            [r for r in results if _sparql_loose(r)], key=_sort_key_result
        )
        fps = {
            r.get("sparql_fingerprint")
            for r in relaxed
            if r.get("sparql_fingerprint")
        }
        if len(fps) == 1:
            fp = next(iter(fps))
            matches = [r for r in relaxed if r.get("sparql_fingerprint") == fp]
            mode = (
                "iri_source_shape_sparql_fingerprint"
                if use_iri
                else "core_signature_sparql_fingerprint"
            )
        else:
            matches = relaxed
            mode = (
                "iri_source_shape_sparql_candidates"
                if use_iri
                else "core_signature_sparql_candidates"
            )

    if len(matches) == 0 and (path == "" or not is_absolute_iri(path)):
        # Blank/complex resultPath ids are unstable across parses.
        def _loose_ok(r: dict[str, Any]) -> bool:
            if r.get("focus_key") != focus_key:
                return False
            if str(r.get("source_constraint_component", "")) != component:
                return False
            if str(r.get("severity", "")) != severity:
                return False
            if use_iri and source_shape is not None:
                if str(r.get("source_shape", "")) != source_shape:
                    return False
            if not sparql_constraints_match(
                row_fp=r.get("sparql_fingerprint"),
                designated_fp=sparql_fingerprint,
                component=component,
            ):
                return False
            if path_fingerprint is not None:
                return r.get("path_fingerprint") == path_fingerprint
            # Without a fingerprint, do not match IRI PredicatePaths by accident.
            return not is_absolute_iri(str(r.get("result_path", "") or ""))

        relaxed = [r for r in results if _loose_ok(r)]
        fps = {
            r.get("path_fingerprint")
            for r in relaxed
            if r.get("path_fingerprint") not in (None, "")
        }
        if len(fps) > 1:
            raise DesignateError(
                "designated baseline failure matched multiple distinct path "
                f"fingerprints ({len(fps)}). Pass --source-shape or "
                "--designation-index after narrowing to a unique path structure"
            )
        if path_fingerprint is not None and relaxed:
            mode = (
                "iri_source_shape_path_fingerprint"
                if use_iri
                else "core_signature_path_fingerprint"
            )
        elif use_iri:
            mode = "iri_source_shape_unstable_path_ignored"
        else:
            mode = "core_signature_path_elided"
        matches = sorted(relaxed, key=_sort_key_result)

    if len(matches) == 0:
        hint = ""
        if path and not is_absolute_iri(path) and not path_fingerprint:
            hint = (
                ". Non-IRI resultPath values (blank/complex paths) are process-"
                "local RDFLib ids. Supply a resolvable source_shape so a "
                "structural path fingerprint can be computed"
            )
        raise DesignateError(
            "designated baseline failure matched 0 ValidationResults" + hint
        )

    if len(matches) > 1:
        if designation_index is None:
            raise DesignateError(
                "designated baseline failure matched "
                f"{len(matches)} ValidationResults. Pass --designation-index "
                f"(1..{len(matches)}) to disambiguate:\n"
                f"{_format_candidates(matches)}"
            )
        if designation_index < 1 or designation_index > len(matches):
            raise DesignateError(
                f"designation-index {designation_index} out of range "
                f"1..{len(matches)}:\n{_format_candidates(matches)}"
            )
        chosen = matches[designation_index - 1]
        mode = f"{mode}_with_index"
    else:
        if designation_index is not None and designation_index != 1:
            raise DesignateError(
                f"designation-index {designation_index} out of range 1..1"
            )
        chosen = matches[0]

    chosen = dict(chosen)
    chosen["_designation_mode"] = mode
    return chosen


def find_parent_node_shapes(shapes: Graph, property_shape: Node) -> list[Node]:
    return sorted(shapes.subjects(SH.property, property_shape), key=str)


def _component_parameter(component: str) -> URIRef | None:
    """Ordinary minCount/maxCount parameter only. Never qualified cardinality."""
    if component == str(SH.MinCountConstraintComponent):
        return SH.minCount
    if component == str(SH.MaxCountConstraintComponent):
        return SH.maxCount
    return None


def _shape_has_path(shapes: Graph, shape: Node, path: str) -> bool:
    return path in {str(p) for p in shapes.objects(shape, SH.path)}


def _alignment_path_ok(
    shapes_baseline: Graph,
    shapes_after: Graph,
    shape_baseline: Node,
    shape_after: Node,
    designated_path: str,
    designated_fp: str | None = None,
) -> tuple[bool, str | None]:
    """Whether the designated path justifies shape alignment across graphs."""
    fp_after = shape_path_fingerprint(shapes_after, shape_after)

    if designated_path == "" and designated_fp in (None, ""):
        if list(shapes_baseline.objects(shape_baseline, SH.path)):
            return False, "empty_result_path_but_baseline_shape_declares_sh_path"
        if list(shapes_after.objects(shape_after, SH.path)):
            return False, "empty_result_path_but_aligned_shape_declares_sh_path"
        return True, None

    if designated_fp is not None:
        if fp_after is None:
            return False, "aligned_shape_path_fingerprint_unavailable"
        if fp_after != designated_fp:
            return False, "path_fingerprint_mismatch"
        return True, None

    if is_absolute_iri(designated_path):
        if not _shape_has_path(shapes_after, shape_after, designated_path):
            return False, "same_iri_present_but_path_mismatch_or_missing"
        return True, None

    fp_base = shape_path_fingerprint(shapes_baseline, shape_baseline)
    if fp_base is None or fp_after is None:
        return False, "path_fingerprint_unavailable"
    if fp_base != fp_after:
        return False, "path_fingerprint_mismatch"
    return True, None


def _parents_link(shapes: Graph, parent: Node, prop: Node) -> bool:
    return (parent, SH.property, prop) in shapes


def align_source_shape(
    shapes_baseline: Graph,
    shapes_after: Graph,
    source_shape: str,
    path: str,
    component: str,
    path_fingerprint: str | None = None,
) -> dict[str, Any]:
    param = _component_parameter(component)
    baseline_node = resolve_shape_node(shapes_baseline, source_shape)
    designated_fp = path_fingerprint
    if designated_fp is None and baseline_node is not None:
        designated_fp = shape_path_fingerprint(shapes_baseline, baseline_node)

    if baseline_node is not None and is_absolute_iri(source_shape):
        baseline_parents = find_parent_node_shapes(shapes_baseline, baseline_node)
        subject_defined = any(shapes_after.triples((baseline_node, None, None)))
        if subject_defined:
            path_ok, path_reason = _alignment_path_ok(
                shapes_baseline,
                shapes_after,
                baseline_node,
                baseline_node,
                path,
                designated_fp=designated_fp,
            )
            if not path_ok:
                return {
                    "shape_alignment": "UNRESOLVED",
                    "aligned_source_shape": None,
                    "reason": path_reason
                    or "same_iri_present_but_path_mismatch_or_missing",
                }
            if baseline_parents:
                linked = [
                    p
                    for p in baseline_parents
                    if any(shapes_after.triples((p, None, None)))
                    and _parents_link(shapes_after, p, baseline_node)
                ]
                if not linked:
                    return {
                        "shape_alignment": "UNRESOLVED",
                        "aligned_source_shape": None,
                        "reason": "same_iri_present_but_parent_property_link_missing",
                    }
            param_status = "NOT_APPLICABLE"
            if param is not None:
                vals = list(shapes_after.objects(baseline_node, param))
                param_status = "PRESENT" if vals else "ABSENT"
            reason = "same_iri_with_matching_path_and_parent_context"
            if path == "" and designated_fp in (None, ""):
                reason = "same_iri_node_level_shape_no_property_path"
            elif designated_fp and not is_absolute_iri(path):
                reason = "same_iri_with_matching_path_fingerprint"
            return {
                "shape_alignment": "ALIGNED",
                "aligned_source_shape": source_shape,
                "reason": reason,
                "constraint_parameter_status": param_status,
                "path_fingerprint": designated_fp,
            }

    if baseline_node is None:
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "baseline_source_shape_not_resolvable_in_shapes_graph",
        }

    if designated_fp is None and not is_absolute_iri(path) and path != "":
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "path_fingerprint_unavailable",
        }

    baseline_parents = find_parent_node_shapes(shapes_baseline, baseline_node)
    if not baseline_parents:
        return {
            "shape_alignment": "UNRESOLVED",
            "aligned_source_shape": None,
            "reason": "baseline_source_shape_has_no_parent_node_shape",
        }

    candidates: list[str] = []
    for parent in baseline_parents:
        if not any(shapes_after.triples((parent, None, None))):
            continue
        for ps in shapes_after.objects(parent, SH.property):
            path_ok, _ = _alignment_path_ok(
                shapes_baseline,
                shapes_after,
                baseline_node,
                ps,
                path,
                designated_fp=designated_fp,
            )
            if path_ok:
                candidates.append(str(ps))

    unique = sorted(set(candidates))
    if len(unique) == 1:
        aligned = resolve_shape_node(shapes_after, unique[0])
        if aligned is None:
            aligned_node: Node = (
                URIRef(unique[0]) if is_absolute_iri(unique[0]) else BNode(unique[0])
            )
        else:
            aligned_node = aligned
        param_status = "NOT_APPLICABLE"
        if param is not None:
            vals = list(shapes_after.objects(aligned_node, param))
            param_status = "PRESENT" if vals else "ABSENT"
        return {
            "shape_alignment": "ALIGNED",
            "aligned_source_shape": unique[0],
            "reason": "unique_parent_path_fingerprint",
            "constraint_parameter_status": param_status,
            "path_fingerprint": designated_fp,
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
        "path_fingerprint": designated_fp,
    }


def match_designated_after(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
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
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        )
    ]
    if direct:
        return direct, "focus_key"

    if not is_absolute_iri(source_shape):
        core = _sorted_core_matches(
            results,
            focus_key=focus_key,
            path=path,
            component=component,
            severity=severity,
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        )
        if len(core) == 1:
            return core, "core_signature_unique"
        if len(core) > 1:
            return core, "core_signature_ambiguous"

    if (
        component == SPARQL_CONSTRAINT_COMPONENT
        and sparql_fingerprint is not None
        and is_absolute_iri(source_shape)
    ):
        fp_hits = [
            r
            for r in results
            if r.get("focus_key") == focus_key
            and str(r.get("source_constraint_component", "")) == component
            and str(r.get("severity", "")) == severity
            and str(r.get("source_shape", "")) == source_shape
            and r.get("sparql_fingerprint") == sparql_fingerprint
            and paths_match(
                row_path=str(r.get("result_path", "") or ""),
                row_fp=r.get("path_fingerprint"),
                designated_path=path,
                designated_fp=path_fingerprint,
            )
        ]
        if fp_hits:
            return fp_hits, "sparql_fingerprint"

    if focus_key.startswith("bnode["):
        return [], "blank_focus_key_unmatched"
    return [], "focus_key"


def original_cardinality_parameter(
    shapes: Graph,
    source_shape: str,
    component: str,
) -> tuple[URIRef, list[str]] | None:
    shape = resolve_shape_node(shapes, source_shape)
    if shape is None:
        return None
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


def _verified_iri_predicate_path(
    shapes: Graph,
    source_shape: str,
    path: str,
) -> tuple[URIRef | None, str | None]:
    """PredicatePath URIRef only for verified IRI sh:path. Else None."""
    if not is_absolute_iri(path):
        return None, "designated_path_not_iri_predicate_path"

    shape = resolve_shape_node(shapes, source_shape)
    if shape is None:
        return None, "source_shape_not_resolvable_for_path_verification"

    declared = list(shapes.objects(shape, SH.path))
    if not declared:
        return None, "source_shape_has_no_sh_path"
    if any(isinstance(p, BNode) for p in declared):
        return None, "shape_path_not_iri_predicate_path"

    iri_paths = [p for p in declared if isinstance(p, URIRef)]
    if len(iri_paths) != 1 or str(iri_paths[0]) != path:
        return None, "designated_path_not_verified_on_source_shape"
    return iri_paths[0], None


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

    predicate, path_reason = _verified_iri_predicate_path(
        shapes_baseline, source_shape, path
    )
    if predicate is None:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": path_reason or "designated_path_not_iri_predicate_path",
            "parameter": str(parameter),
        }

    focus_node, resolve_reason = _resolve_focus(data, focus_key, focus_key_properties)
    if focus_node is None:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": resolve_reason or "focus_node_not_found_in_data",
        }

    count = len(list(data.objects(focus_node, predicate)))
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


def _path_unstable(path: str, path_fingerprint: str | None = None) -> bool:

    if path_fingerprint is not None:
        return False
    return path != "" and not is_absolute_iri(path)


def _same_constraint_instance_rows(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> tuple[list[dict[str, Any]], str]:

    return match_designated_after(
        results,
        focus_key=focus_key,
        path=path,
        source_shape=source_shape,
        component=component,
        severity=severity,
        path_fingerprint=path_fingerprint,
        sparql_fingerprint=sparql_fingerprint,
    )


def _possible_missed_violation_due_to_path(
    results: list[dict[str, Any]],
    *,
    focus_key: str,
    source_shape: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
) -> bool:

    if path_fingerprint is not None:
        return False
    for r in results:
        if r.get("focus_key") != focus_key:
            continue
        if str(r.get("source_constraint_component", "")) != component:
            continue
        if str(r.get("severity", "")) != severity:
            continue
        if is_absolute_iri(source_shape) and str(r.get("source_shape", "")) != source_shape:
            continue
        if not is_absolute_iri(str(r.get("result_path", "") or "")):
            return True
    return False


def evaluate_original_constraint_from_s0_results(
    s0_results: list[dict[str, Any]],
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
    targeted: bool,
    data_graph: Graph | None = None,
    focus_key_properties: list[URIRef] | None = None,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Evaluate the designated constraint via V(data, S0) results.

    SATISFIED / VIOLATED apply only to that instance, not graph-wide conforms.
    """
    method = "s0_validation_result_filter"

    if not targeted:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "focus_not_targeted",
            "method": method,
        }

    if (
        component_requires_structural_fingerprint(
            component, designated_fp=sparql_fingerprint
        )
        or is_structural_constraint_fingerprint(sparql_fingerprint)
    ) and not sparql_fingerprint:
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "sparql_constraint_fingerprint_unavailable",
            "method": method,
        }

    blank_focus_uniquely_resolved = False
    if focus_key.startswith("bnode["):
        if data_graph is None:
            return {
                "original_constraint_evaluation": "NOT_EVALUATED",
                "reason": "blank_focus_requires_data_graph_for_identity",
                "method": method,
            }
        focus_node, resolve_reason = _resolve_focus(
            data_graph, focus_key, focus_key_properties or []
        )
        if focus_node is None:
            return {
                "original_constraint_evaluation": "NOT_EVALUATED",
                "reason": resolve_reason or "blank_focus_identity_unresolved",
                "method": method,
            }
        blank_focus_uniquely_resolved = True

    matches, match_mode = _same_constraint_instance_rows(
        s0_results,
        focus_key=focus_key,
        path=path,
        source_shape=source_shape,
        component=component,
        severity=severity,
        path_fingerprint=path_fingerprint,
        sparql_fingerprint=sparql_fingerprint,
    )

    # No VR matched. Unique blank focus may still be SATISFIED (same as CLEAR).
    if match_mode == "blank_focus_key_unmatched":
        if not blank_focus_uniquely_resolved:
            return {
                "original_constraint_evaluation": "NOT_EVALUATED",
                "reason": "blank_focus_key_unmatched",
                "method": method,
                "match_mode": match_mode,
            }
        match_mode = "blank_focus_key_absent_vr_identity_ok"

    if match_mode == "core_signature_ambiguous":
        return {
            "original_constraint_evaluation": "VIOLATED",
            "reason": "designated_constraint_instance_still_reports_results",
            "method": method,
            "match_mode": match_mode,
            "matching_result_count": len(matches),
            "instance_identity": "component_signature_non_unique_values",
        }

    if matches:
        return {
            "original_constraint_evaluation": "VIOLATED",
            "reason": "designated_constraint_instance_still_reports_results",
            "method": method,
            "match_mode": match_mode,
            "matching_result_count": len(matches),
        }

    if _path_unstable(path, path_fingerprint) and _possible_missed_violation_due_to_path(
        s0_results,
        focus_key=focus_key,
        source_shape=source_shape,
        component=component,
        severity=severity,
        path_fingerprint=path_fingerprint,
    ):
        return {
            "original_constraint_evaluation": "NOT_EVALUATED",
            "reason": "unstable_result_path_may_hide_matching_violation",
            "method": method,
            "match_mode": match_mode,
        }

    if component == SPARQL_CONSTRAINT_COMPONENT or is_structural_constraint_fingerprint(
        sparql_fingerprint
    ):
        for r in s0_results:
            if r.get("focus_key") != focus_key:
                continue
            if str(r.get("source_constraint_component", "")) != component:
                continue
            if str(r.get("severity", "")) != severity:
                continue
            if is_absolute_iri(source_shape) and str(r.get("source_shape", "")) != source_shape:
                continue
            if r.get("sparql_fingerprint") is None:
                return {
                    "original_constraint_evaluation": "NOT_EVALUATED",
                    "reason": "sparql_result_missing_fingerprint_may_hide_match",
                    "method": method,
                    "match_mode": match_mode,
                }

    return {
        "original_constraint_evaluation": "SATISFIED",
        "reason": "designated_constraint_instance_absent_from_s0_results",
        "method": method,
        "match_mode": match_mode,
    }


def combine_original_with_cardinality_crosscheck(
    vr_result: dict[str, Any],
    card_result: dict[str, Any],
) -> dict[str, Any]:

    vr = vr_result.get("original_constraint_evaluation")
    card = card_result.get("original_constraint_evaluation")
    out = dict(vr_result)
    out["cardinality_crosscheck"] = card_result

    if card in ("SATISFIED", "VIOLATED") and vr in ("SATISFIED", "VIOLATED"):
        if card != vr:
            return {
                "original_constraint_evaluation": "NOT_EVALUATED",
                "reason": "cardinality_and_s0_result_filter_disagree",
                "method": "disagreement_guard",
                "s0_validation_result_filter": vr_result,
                "cardinality_crosscheck": card_result,
            }
        out["cardinality_crosscheck_status"] = "AGREE"
    elif card in ("SATISFIED", "VIOLATED") and vr == "NOT_EVALUATED":
        out["cardinality_crosscheck_status"] = "CARDINALITY_ONLY_EVALUATED"
    elif vr in ("SATISFIED", "VIOLATED") and card == "NOT_EVALUATED":
        out["cardinality_crosscheck_status"] = "FILTER_ONLY_EVALUATED"
    else:
        out["cardinality_crosscheck_status"] = "BOTH_NOT_EVALUATED"
    return out
