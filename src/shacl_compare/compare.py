from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import BNode, URIRef
from rdflib.namespace import SH

from shacl_compare import __version__
from shacl_compare.designate import (
    DesignateError,
    align_source_shape,
    combine_original_with_cardinality_crosscheck,
    evaluate_original_cardinality_on_focus,
    evaluate_original_constraint_from_s0_results,
    find_parent_node_shapes,
    is_absolute_iri,
    match_designated_after,
    resolve_shape_node,
    select_designated,
)
from shacl_compare.formal import ORIGINAL_CONSTRAINT_SEMANTICS
from shacl_compare.diff import MAX_TRIPLES_FOR_ISO, diff_graphs
from shacl_compare.graph_io import load_graph
from shacl_compare.paths import (
    paths_match,
    resolve_designation_path_fingerprint,
    shape_path_fingerprint_str,
)
from shacl_compare.custom_constraint_components import is_user_constraint_component
from shacl_compare.sparql_constraints import (
    SPARQL_CONSTRAINT_COMPONENT,
    component_requires_structural_fingerprint,
    is_structural_constraint_fingerprint,
)
from shacl_compare.requirements import (
    assess_cardinality_condition,
    load_requirement_card,
)
from shacl_compare.targets import all_targets, membership_for_focus
from shacl_compare.terms import node_focus_key
from shacl_compare.validation import run_validation, validator_meta


@dataclass
class CompareConfig:
    data_baseline: Path
    shapes_baseline: Path
    data_repair: Path
    shapes_revision: Path
    focus: str
    path: str
    source_shape: str | None
    component: str
    severity: str
    focus_key_properties: list[str]
    requirement_card: Path | None
    out: Path
    designation_index: int | None = None


def _focus_props(iris: list[str]) -> list[URIRef]:
    return [URIRef(x) for x in iris]


def _signature(
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {
        "focus_key": focus_key,
        "result_path": path,
        "source_shape": source_shape,
        "source_constraint_component": component,
        "severity": severity,
    }
    if path_fingerprint is not None:
        out["path_fingerprint"] = path_fingerprint
    if sparql_fingerprint is not None:
        out["sparql_fingerprint"] = sparql_fingerprint
    return out


def _target_status(before: bool, after: bool) -> str:
    if before and after:
        return "RETAINED"
    if before and not after:
        return "LOST"
    if not before and after:
        return "GAINED"
    return "NOT_APPLICABLE"


def _focus_key_resolvable(
    data,
    focus_key: str,
    focus_key_properties: list[URIRef],
) -> str:
    if not focus_key.startswith("bnode["):
        return "iri"
    hits = [
        s
        for s in set(data.subjects())
        if node_focus_key(data, s, focus_key_properties) == focus_key
    ]
    if len(hits) == 1:
        return "unique"
    if len(hits) == 0:
        return "missing"
    return "ambiguous"


def _other_focus_rows(
    baseline_results: list[dict[str, Any]],
    after_results: list[dict[str, Any]],
    *,
    designated_focus_key: str,
    path: str,
    component: str,
    severity: str,
    source_shapes: set[str],
    path_fingerprint: str | None = None,
    sparql_fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    def relevant(results: list[dict[str, Any]]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for r in results:
            if str(r.get("source_constraint_component", "")) != component:
                continue
            if str(r.get("severity", "")) != severity:
                continue
            if str(r.get("source_shape", "")) not in source_shapes:
                continue
            if not paths_match(
                row_path=str(r.get("result_path", "") or ""),
                row_fp=r.get("path_fingerprint"),
                designated_path=path,
                designated_fp=path_fingerprint,
            ):
                continue
            if component_requires_structural_fingerprint(
                component, designated_fp=sparql_fingerprint
            ) or is_structural_constraint_fingerprint(sparql_fingerprint):
                if sparql_fingerprint is None:
                    continue
                if r.get("sparql_fingerprint") != sparql_fingerprint:
                    continue
            fk = str(r.get("focus_key", ""))
            if fk and fk != designated_focus_key:
                out[fk] = True
        return out

    before = relevant(baseline_results)
    after = relevant(after_results)
    rows = []
    for fk in sorted(set(before) | set(after)):
        b = before.get(fk, False)
        a = after.get(fk, False)
        if b and a:
            outcome = "PERSIST"
        elif b and not a:
            outcome = "CLEAR"
        else:
            outcome = "NEW"
        rows.append({"focus_key": fk, "result_outcome": outcome})
    return rows


def _path_identity(r: dict[str, Any]) -> str:
    fp = r.get("path_fingerprint")
    if fp is not None and fp != "":
        return f"fp:{fp}"
    rp = str(r.get("result_path", "") or "")
    if is_absolute_iri(rp) or rp == "":
        return rp
    return f"unstable:{rp}"


def _sparql_identity(r: dict[str, Any]) -> str:
    fp = r.get("sparql_fingerprint")
    if fp:
        return f"sparql:{fp}"
    sc = r.get("source_constraint")
    if sc:
        return f"sc:{sc}"
    return ""


def _result_signature(r: dict[str, Any]) -> tuple[str, ...]:
    value = r.get("value", "")
    if isinstance(value, list):
        value = "|".join(sorted(str(v) for v in value))
    return (
        str(r.get("focus_key", "")),
        _path_identity(r),
        str(r.get("source_shape", "")),
        str(r.get("source_constraint_component", "")),
        str(r.get("severity", "")),
        _sparql_identity(r),
        str(value),
    )


def _designated_path_identity(designated: dict[str, str]) -> str:
    fp = designated.get("path_fingerprint")
    if fp is not None and fp != "":
        return f"fp:{fp}"
    rp = designated.get("result_path", "")
    if is_absolute_iri(rp) or rp == "":
        return rp
    return f"unstable:{rp}"


def _designated_sparql_identity(designated: dict[str, str]) -> str:
    fp = designated.get("sparql_fingerprint")
    if fp:
        return f"sparql:{fp}"
    return ""


def _is_designated_signature(sig: tuple[str, ...], designated: dict[str, str]) -> bool:
    path_id = _designated_path_identity(designated)
    sparql_id = _designated_sparql_identity(designated)
    if sig[:6] == (
        designated["focus_key"],
        path_id,
        designated["source_shape"],
        designated["source_constraint_component"],
        designated["severity"],
        sparql_id,
    ):
        return True
    # Blank sourceShape ids differ across S0 vs SB. Match without that field.
    if not is_absolute_iri(designated["source_shape"]):
        return (
            sig[0] == designated["focus_key"]
            and sig[1] == path_id
            and sig[3] == designated["source_constraint_component"]
            and sig[4] == designated["severity"]
            and sig[5] == sparql_id
        )
    return False


def _residuals_and_new(
    baseline_results: list[dict[str, Any]],
    after_results: list[dict[str, Any]],
    designated: dict[str, str],
) -> dict[str, Any]:
    before = Counter(_result_signature(r) for r in baseline_results)
    after = Counter(_result_signature(r) for r in after_results)
    persisted: list[dict[str, Any]] = []
    cleared: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    for sig in sorted(set(before) | set(after)):
        if _is_designated_signature(sig, designated):
            continue
        b = before[sig]
        a = after[sig]
        row = {"signature": list(sig), "baseline_count": b, "after_count": a}
        if b and a:
            persisted.append(row)
            if a < b:
                cleared.append(
                    {
                        "signature": list(sig),
                        "baseline_count": b,
                        "after_count": a,
                        "cleared_count": b - a,
                    }
                )
            elif a > b:
                new.append(
                    {
                        "signature": list(sig),
                        "baseline_count": b,
                        "after_count": a,
                        "new_count": a - b,
                    }
                )
        elif b and not a:
            cleared.append(
                {
                    "signature": list(sig),
                    "baseline_count": b,
                    "after_count": 0,
                    "cleared_count": b,
                }
            )
        else:
            new.append(
                {
                    "signature": list(sig),
                    "baseline_count": 0,
                    "after_count": a,
                    "new_count": a,
                }
            )
    return {
        "persisted": persisted,
        "cleared": cleared,
        "new": new,
        "signature_includes_value": True,
    }


def _original_constraint_for_branch(
    *,
    s0_results: list[dict[str, Any]],
    data_after,
    shapes_baseline,
    designated: dict[str, str],
    focus_key_properties: list[URIRef],
    targeted_under_s0: bool,
) -> dict[str, Any]:
    focus_key = designated["focus_key"]
    path = designated["result_path"]
    component = designated["source_constraint_component"]
    severity = designated["severity"]
    source_shape = designated["source_shape"]

    vr = evaluate_original_constraint_from_s0_results(
        s0_results,
        focus_key=focus_key,
        path=path,
        source_shape=source_shape,
        component=component,
        severity=severity,
        targeted=targeted_under_s0,
        data_graph=data_after,
        focus_key_properties=focus_key_properties,
        path_fingerprint=designated.get("path_fingerprint"),
        sparql_fingerprint=designated.get("sparql_fingerprint"),
    )
    card = evaluate_original_cardinality_on_focus(
        data_after,
        shapes_baseline,
        focus_key=focus_key,
        path=path,
        source_shape=source_shape,
        component=component,
        focus_key_properties=focus_key_properties,
        targeted=targeted_under_s0,
    )
    return combine_original_with_cardinality_crosscheck(vr, card)


def _analyse_branch(
    *,
    label: str,
    baseline_results: list[dict[str, Any]],
    after_validation: dict[str, Any],
    data_after,
    shapes_after,
    shapes_baseline,
    data_for_original,
    s0_results_for_original: list[dict[str, Any]],
    designated: dict[str, str],
    focus_key_properties: list[URIRef],
    is_revision: bool,
) -> dict[str, Any]:
    focus_key = designated["focus_key"]
    path = designated["result_path"]
    component = designated["source_constraint_component"]
    severity = designated["severity"]
    source_shape = designated["source_shape"]
    path_fingerprint = designated.get("path_fingerprint")
    sparql_fingerprint = designated.get("sparql_fingerprint")

    alignment = {
        "shape_alignment": "ALIGNED",
        "aligned_source_shape": source_shape,
        "reason": "shapes_unchanged_interface_reuses_S0",
    }
    match_shape = source_shape
    if is_revision:
        alignment = align_source_shape(
            shapes_baseline,
            shapes_after,
            source_shape,
            path,
            component,
            path_fingerprint=path_fingerprint,
        )
        if alignment["shape_alignment"] != "ALIGNED":
            targets_before = all_targets(
                data_for_original, shapes_baseline, focus_key_properties
            )
            targets_after = all_targets(
                data_after, shapes_after, focus_key_properties
            )
            memb_b = membership_for_focus(
                targets_before, focus_key, source_shape, shapes_baseline
            )
            memb_a = membership_for_focus(
                targets_after, focus_key, source_shape, shapes_baseline
            )
            original = _original_constraint_for_branch(
                s0_results=s0_results_for_original,
                data_after=data_after,
                shapes_baseline=shapes_baseline,
                designated=designated,
                focus_key_properties=focus_key_properties,
                targeted_under_s0=memb_b["targeted"],
            )
            return {
                "label": label,
                "conforms": after_validation["conforms"],
                "result_count": after_validation["result_count"],
                "results": after_validation["results"],
                "result_outcome": "NOT_COMPARABLE",
                "designated_match_mode": "shape_alignment_unresolved",
                "shape_alignment": alignment["shape_alignment"],
                "shape_alignment_detail": alignment,
                "target_membership": _target_status(
                    memb_b["targeted"], memb_a["targeted"]
                ),
                "target_membership_detail": {
                    "before": memb_b,
                    "after": memb_a,
                },
                "original_constraint_evaluation": original,
                "other_focus_nodes": [],
                "residual_results": _residuals_and_new(
                    baseline_results, after_validation["results"], designated
                ),
            }
        match_shape = alignment["aligned_source_shape"]

    if (
        component == SPARQL_CONSTRAINT_COMPONENT
        or is_structural_constraint_fingerprint(sparql_fingerprint)
        or component_requires_structural_fingerprint(
            component, designated_fp=sparql_fingerprint
        )
    ) and not sparql_fingerprint:
        matches, match_mode = [], "sparql_fingerprint_unavailable"
        result_outcome = "NOT_COMPARABLE"
    else:
        matches, match_mode = match_designated_after(
            after_validation["results"],
            focus_key=focus_key,
            path=path,
            source_shape=match_shape,
            component=component,
            severity=severity,
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        )
        if not matches and match_shape != source_shape:
            matches, match_mode = match_designated_after(
                after_validation["results"],
                focus_key=focus_key,
                path=path,
                source_shape=source_shape,
                component=component,
                severity=severity,
                path_fingerprint=path_fingerprint,
                sparql_fingerprint=sparql_fingerprint,
            )

        if matches and match_mode == "core_signature_ambiguous":
            result_outcome = "NOT_COMPARABLE"
        elif matches:
            result_outcome = "PERSIST"
        elif match_mode == "blank_focus_key_unmatched":
            resolvable = _focus_key_resolvable(
                data_after, focus_key, focus_key_properties
            )
            if resolvable == "unique":
                result_outcome = "CLEAR"
                match_mode = "blank_focus_key_absent_vr_identity_ok"
            else:
                result_outcome = "NOT_COMPARABLE"
                match_mode = f"blank_focus_key_unmatched_{resolvable}"
        else:
            result_outcome = "CLEAR"

    targets_before = all_targets(
        data_for_original, shapes_baseline, focus_key_properties
    )
    targets_after = all_targets(data_after, shapes_after, focus_key_properties)
    memb_b = membership_for_focus(
        targets_before, focus_key, source_shape, shapes_baseline
    )
    if is_revision:
        memb_a = membership_for_focus(
            targets_after, focus_key, match_shape, shapes_after
        )
    else:
        memb_a = membership_for_focus(
            targets_after, focus_key, source_shape, shapes_baseline
        )
    target_membership = _target_status(memb_b["targeted"], memb_a["targeted"])

    targeted_under_s0 = memb_a["targeted"] if not is_revision else memb_b["targeted"]
    original = _original_constraint_for_branch(
        s0_results=s0_results_for_original,
        data_after=data_after,
        shapes_baseline=shapes_baseline,
        designated=designated,
        focus_key_properties=focus_key_properties,
        targeted_under_s0=targeted_under_s0,
    )

    other_shapes = {source_shape}
    if match_shape:
        other_shapes.add(match_shape)

    return {
        "label": label,
        "conforms": after_validation["conforms"],
        "result_count": after_validation["result_count"],
        "results": after_validation["results"],
        "result_outcome": result_outcome,
        "designated_match_mode": match_mode,
        "shape_alignment": alignment["shape_alignment"],
        "shape_alignment_detail": alignment,
        "target_membership": target_membership,
        "target_membership_detail": {"before": memb_b, "after": memb_a},
        "original_constraint_evaluation": original,
        "other_focus_nodes": _other_focus_rows(
            baseline_results,
            after_validation["results"],
            designated_focus_key=focus_key,
            path=path,
            component=component,
            severity=severity,
            source_shapes=other_shapes,
            path_fingerprint=path_fingerprint,
            sparql_fingerprint=sparql_fingerprint,
        ),
        "residual_results": _residuals_and_new(
            baseline_results, after_validation["results"], designated
        ),
    }


def _unsupported_construct_flags(
    s0,
    sb,
    path: str,
    path_fingerprint: str | None = None,
    *,
    component: str | None = None,
    sparql_fingerprint: str | None = None,
) -> list[str]:
    flags: list[str] = []
    if path == "" and path_fingerprint in (None, ""):
        flags.append("designated_path_empty_node_level_or_missing_result_path")
    elif not is_absolute_iri(path):
        flags.append("designated_path_not_absolute_iri_predicate_path")
        if not path_fingerprint:
            flags.append("complex_or_blank_result_path_not_stable_across_parses")
    for label, g in (("baseline", s0), ("revision", sb)):
        if any(True for _ in g.triples((None, SH.sparql, None))):
            if (
                component == SPARQL_CONSTRAINT_COMPONENT
                and sparql_fingerprint
            ):
                flags.append(f"shapes_contain_sh_sparql_{label}_matched_via_fingerprint")
            else:
                flags.append(f"shapes_contain_sh_sparql_{label}")
        # Ordinary sh:sparql/sh:ask is unsupported. Custom ASK validators are OK.
        for sparql_node in g.objects(None, SH.sparql):
            if list(g.objects(sparql_node, SH.ask)):
                flags.append(
                    f"shapes_contain_sh_ask_unsupported_by_pyshacl_{label}"
                )
                break
        for obj in g.objects(None, SH.path):
            if isinstance(obj, BNode):
                flags.append(f"shapes_contain_non_iri_path_{label}")
                break
    return sorted(set(flags))


def run_compare(cfg: CompareConfig) -> dict[str, Any]:
    focus_key_properties = _focus_props(cfg.focus_key_properties)

    g0 = load_graph(cfg.data_baseline)
    s0 = load_graph(cfg.shapes_baseline)
    ga = load_graph(cfg.data_repair)
    sb = load_graph(cfg.shapes_revision)

    baseline = run_validation(g0, s0, focus_key_properties)
    after_a = run_validation(ga, s0, focus_key_properties)
    after_b = run_validation(g0, sb, focus_key_properties)

    focus_key = cfg.focus
    designation_mode = "core_signature"
    cli_path_fp = resolve_designation_path_fingerprint(
        s0, path=str(cfg.path or ""), source_shape=cfg.source_shape
    )
    try:
        designated_row = select_designated(
            baseline["results"],
            focus_key=focus_key,
            path=cfg.path,
            source_shape=cfg.source_shape,
            component=cfg.component,
            severity=cfg.severity,
            designation_index=cfg.designation_index,
            path_fingerprint=cli_path_fp,
            sparql_fingerprint=None,
        )
    except DesignateError:
        alt_keys = {
            r.get("focus_key")
            for r in baseline["results"]
            if r.get("focus_node") == cfg.focus or r.get("focus_key") == cfg.focus
        }
        if len(alt_keys) == 1:
            focus_key = next(iter(alt_keys))
            designated_row = select_designated(
                baseline["results"],
                focus_key=focus_key,
                path=cfg.path,
                source_shape=cfg.source_shape,
                component=cfg.component,
                severity=cfg.severity,
                designation_index=cfg.designation_index,
                path_fingerprint=cli_path_fp,
                sparql_fingerprint=None,
            )
        else:
            raise

    designation_mode = str(designated_row.pop("_designation_mode", designation_mode))
    resolved_source_shape = str(designated_row.get("source_shape", ""))
    if not resolved_source_shape:
        raise DesignateError(
            "designated baseline result is missing sh:sourceShape"
        )
    resolved_path = str(designated_row.get("result_path", "") or "")
    cli_path = str(cfg.path or "")
    if is_absolute_iri(cli_path) and resolved_path != cli_path:
        raise DesignateError(
            "designated resultPath does not match --path "
            f"(result={resolved_path!r}, cli={cli_path!r}). "
            "Refusing to continue with an ambiguous path identity"
        )

    resolved_fp = designated_row.get("path_fingerprint")
    if resolved_fp is None:
        resolved_fp = shape_path_fingerprint_str(s0, resolved_source_shape)
    if resolved_fp is None:
        resolved_fp = cli_path_fp

    resolved_sparql_fp = designated_row.get("sparql_fingerprint")
    if cfg.component == SPARQL_CONSTRAINT_COMPONENT and not resolved_sparql_fp:
        raise DesignateError(
            "designated SPARQLConstraintComponent result lacks a structural "
            "sparql_fingerprint. Refusing ambiguous SPARQL constraint identity"
        )
    if is_user_constraint_component(s0, cfg.component) and not resolved_sparql_fp:
        raise DesignateError(
            "designated custom ConstraintComponent result lacks a structural "
            "CUSTOMCC fingerprint (component/parameters/validator). Refusing "
            "ambiguous custom constraint-component identity"
        )

    designated = _signature(
        focus_key=focus_key,
        path=resolved_path,
        source_shape=resolved_source_shape,
        component=cfg.component,
        severity=cfg.severity,
        path_fingerprint=resolved_fp,
        sparql_fingerprint=resolved_sparql_fp,
    )

    data_diff = diff_graphs(g0, ga)
    shapes_diff = diff_graphs(s0, sb)

    intervention_a = _analyse_branch(
        label="A_data_repair",
        baseline_results=baseline["results"],
        after_validation=after_a,
        data_after=ga,
        shapes_after=s0,
        shapes_baseline=s0,
        data_for_original=g0,
        s0_results_for_original=after_a["results"],
        designated=designated,
        focus_key_properties=focus_key_properties,
        is_revision=False,
    )
    intervention_b = _analyse_branch(
        label="B_constraint_revision",
        baseline_results=baseline["results"],
        after_validation=after_b,
        data_after=g0,
        shapes_after=sb,
        shapes_baseline=s0,
        data_for_original=g0,
        s0_results_for_original=baseline["results"],
        designated=designated,
        focus_key_properties=focus_key_properties,
        is_revision=True,
    )

    requirement_section: dict[str, Any] | None = None
    if cfg.requirement_card is not None:
        card = load_requirement_card(cfg.requirement_card)
        requirement_section = {
            "card": {k: v for k, v in card.items() if k != "parameter_iri"},
            "on_baseline_shapes": assess_cardinality_condition(s0, card),
            "on_revision_shapes": assess_cardinality_condition(sb, card),
            "note": (
                "Assesses only whether the named cardinality parameter is present "
                "as specified, not general domain correctness or full profile compliance."
            ),
        }

    undetermined = [
        "factual_or_domain_correctness",
        "ranking_or_preference_between_A_and_B",
        "cost_equivalence_of_data_edits_and_shape_edits",
        "full_profile_or_specification_conformance_beyond_named_cardinality_condition",
    ]
    if data_diff["diff_status"] == "AMBIGUOUS":
        undetermined.append("exact_data_triple_edit_list")
    if shapes_diff["diff_status"] == "AMBIGUOUS":
        undetermined.append("exact_shapes_triple_edit_list")
    if intervention_b["shape_alignment"] == "UNRESOLVED":
        undetermined.append("designated_failure_matching_under_revised_shapes")
    if intervention_a["target_membership"] == "LOST":
        undetermined.append(
            "whether_A_clearance_reflects_constraint_satisfaction_or_target_loss"
        )
    if intervention_b["target_membership"] == "LOST":
        undetermined.append(
            "whether_B_clearance_reflects_constraint_satisfaction_or_target_loss"
        )
    for branch, name in (
        (intervention_a, "A"),
        (intervention_b, "B"),
    ):
        if branch["result_outcome"] == "NOT_COMPARABLE":
            undetermined.append(f"designated_result_identity_{name}")

    unsupported = _unsupported_construct_flags(
        s0,
        sb,
        designated["result_path"],
        path_fingerprint=designated.get("path_fingerprint"),
        component=designated["source_constraint_component"],
        sparql_fingerprint=designated.get("sparql_fingerprint"),
    )
    undetermined.extend(unsupported)

    if designated["focus_key"].startswith("bnode["):
        undetermined.append(
            "blank_focus_identity_depends_on_stable_content_key_properties"
        )

    noop_warnings = []
    if data_diff.get("unchanged") is True:
        noop_warnings.append("data_repair_is_noop_relative_to_baseline_data")
    if shapes_diff.get("unchanged") is True:
        noop_warnings.append("constraint_revision_is_noop_relative_to_baseline_shapes")

    resolved_node = resolve_shape_node(s0, resolved_source_shape)
    parents = (
        find_parent_node_shapes(s0, resolved_node) if resolved_node is not None else []
    )

    return {
        "meta": {
            "tool": "shacl-compare",
            "version": __version__,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version.split()[0],
            "rdflib_version": __import__("rdflib").__version__,
            "validator": validator_meta(),
            "diff_iso_size_bound": {
                "max_combined_triples": MAX_TRIPLES_FOR_ISO,
                "role": "provisional_performance_safeguard",
                "not_a_benchmarked_threshold": True,
                "no_wall_clock_limit": True,
            },
            "interface": {
                "A_validates_with": "S0",
                "B_validates_with": "G0",
                "note": (
                    "Four-file interface: A reuses baseline shapes S0. "
                    "B reuses baseline data G0."
                ),
            },
            "supported_scope_note": (
                "Designated CLEAR/PERSIST comparison covers SHACL Core property "
                "shapes with IRI PredicatePaths, all seven W3C property-path "
                "forms via fingerprints, SHACL-SPARQL sh:sparql/SELECT "
                "constraints via query fingerprints, and user-defined "
                "SPARQL-based constraint components via CUSTOMCC fingerprints "
                "(component IRI, parameter bindings, and validator query). "
                "pySHACL 0.40.x runs these with advanced=False. Standard targets "
                "are supported (targetClass, implicit class, targetNode, "
                "targetSubjectsOf, targetObjectsOf). Anonymous property shapes "
                "use focus/path/component/severity designation, with optional "
                "--designation-index. Identical paths or SPARQL/CUSTOMCC "
                "fingerprints without unique shape identity are NOT_COMPARABLE. "
                "Original-constraint evaluation filters V(GA,S0) and V(G0,S0) "
                "for the designated instance and does not use graph-wide "
                "conforms. Ordinary sh:sparql with sh:ask is unsupported in "
                "pySHACL 0.40.x. SHACL Advanced Features are out of scope."
            ),
            "original_constraint_semantics": ORIGINAL_CONSTRAINT_SEMANTICS,
        },
        "inputs": {
            "data_baseline": str(cfg.data_baseline),
            "shapes_baseline": str(cfg.shapes_baseline),
            "data_repair": str(cfg.data_repair),
            "shapes_revision": str(cfg.shapes_revision),
            "requirement_card": (
                str(cfg.requirement_card) if cfg.requirement_card else None
            ),
            "source_shape_cli": cfg.source_shape,
            "designation_index": cfg.designation_index,
        },
        "designated": {
            **designated,
            "designation_mode": designation_mode,
            "source_shape_is_absolute_iri": is_absolute_iri(resolved_source_shape),
            "baseline_result": designated_row,
            "parent_node_shapes": [str(p) for p in parents],
        },
        "baseline": {
            "conforms": baseline["conforms"],
            "result_count": baseline["result_count"],
            "results": baseline["results"],
        },
        "data_diff": data_diff,
        "shapes_diff": shapes_diff,
        "noop_warnings": noop_warnings,
        "intervention_A": intervention_a,
        "intervention_B": intervention_b,
        "comparison": {
            "designated_result_outcome_A": intervention_a["result_outcome"],
            "designated_result_outcome_B": intervention_b["result_outcome"],
            "target_membership_A": intervention_a["target_membership"],
            "target_membership_B": intervention_b["target_membership"],
            "original_constraint_A": intervention_a["original_constraint_evaluation"],
            "original_constraint_B": intervention_b["original_constraint_evaluation"],
            "global_conforms_A": intervention_a["conforms"],
            "global_conforms_B": intervention_b["conforms"],
            "ranking": None,
            "cost_score": None,
        },
        "requirement_card": requirement_section,
        "undetermined": undetermined,
    }
