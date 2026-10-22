from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import URIRef

from shacl_compare import __version__
from shacl_compare.designate import (
    DesignateError,
    align_source_shape,
    evaluate_original_cardinality_on_focus,
    find_parent_node_shapes,
    match_designated_after,
    select_designated,
)
from shacl_compare.diff import MAX_TRIPLES_FOR_ISO, diff_graphs
from shacl_compare.graph_io import load_graph
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
    source_shape: str
    component: str
    severity: str
    focus_key_properties: list[str]
    requirement_card: Path | None
    out: Path


def _focus_props(iris: list[str]) -> list[URIRef]:
    return [URIRef(x) for x in iris]


def _signature(
    *,
    focus_key: str,
    path: str,
    source_shape: str,
    component: str,
    severity: str,
) -> dict[str, str]:
    return {
        "focus_key": focus_key,
        "result_path": path,
        "source_shape": source_shape,
        "source_constraint_component": component,
        "severity": severity,
    }


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
    """unique | missing | ambiguous | iri"""
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
) -> list[dict[str, Any]]:
    def relevant(results: list[dict[str, Any]]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for r in results:
            if (
                str(r.get("result_path", "")) == path
                and str(r.get("source_constraint_component", "")) == component
                and str(r.get("severity", "")) == severity
                and str(r.get("source_shape", "")) in source_shapes
            ):
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


def _residuals_and_new(
    baseline_results: list[dict[str, Any]],
    after_results: list[dict[str, Any]],
    designated: dict[str, str],
) -> dict[str, Any]:
    def sig(r: dict[str, Any]) -> tuple[str, ...]:
        return (
            str(r.get("focus_key", "")),
            str(r.get("result_path", "")),
            str(r.get("source_shape", "")),
            str(r.get("source_constraint_component", "")),
            str(r.get("severity", "")),
        )

    d_sig = (
        designated["focus_key"],
        designated["result_path"],
        designated["source_shape"],
        designated["source_constraint_component"],
        designated["severity"],
    )
    before = {sig(r) for r in baseline_results}
    after = {sig(r) for r in after_results}

    def drop_designated(items: list[tuple[str, ...]]) -> list[list[str]]:
        return [list(x) for x in items if x != d_sig]

    return {
        "persisted": drop_designated(sorted(before & after)),
        "cleared": drop_designated(sorted(before - after)),
        "new": [list(x) for x in sorted(after - before) if x != d_sig],
    }


def _analyse_branch(
    *,
    label: str,
    baseline_results: list[dict[str, Any]],
    after_validation: dict[str, Any],
    data_after,
    shapes_after,
    shapes_baseline,
    data_for_original,
    designated: dict[str, str],
    focus_key_properties: list[URIRef],
    is_revision: bool,
) -> dict[str, Any]:
    focus_key = designated["focus_key"]
    path = designated["result_path"]
    component = designated["source_constraint_component"]
    severity = designated["severity"]
    source_shape = designated["source_shape"]

    alignment = {
        "shape_alignment": "ALIGNED",
        "aligned_source_shape": source_shape,
        "reason": "shapes_unchanged_interface_reuses_S0",
    }
    match_shape = source_shape
    if is_revision:
        alignment = align_source_shape(
            shapes_baseline, shapes_after, source_shape, path, component
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
                "original_constraint_evaluation": {
                    "original_constraint_evaluation": "NOT_EVALUATED",
                    "reason": "shape_alignment_unresolved",
                },
                "other_focus_nodes": [],
                "residual_results": _residuals_and_new(
                    baseline_results, after_validation["results"], designated
                ),
            }
        match_shape = alignment["aligned_source_shape"]

    matches, match_mode = match_designated_after(
        after_validation["results"],
        focus_key=focus_key,
        path=path,
        source_shape=match_shape,
        component=component,
        severity=severity,
    )
    if not matches and match_shape != source_shape:
        matches, match_mode = match_designated_after(
            after_validation["results"],
            focus_key=focus_key,
            path=path,
            source_shape=source_shape,
            component=component,
            severity=severity,
        )

    if matches:
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

    if not is_revision:
        original = evaluate_original_cardinality_on_focus(
            data_after,
            shapes_baseline,
            focus_key=focus_key,
            path=path,
            source_shape=source_shape,
            component=component,
            focus_key_properties=focus_key_properties,
            targeted=memb_a["targeted"],
        )
    else:
        original = evaluate_original_cardinality_on_focus(
            data_after,
            shapes_baseline,
            focus_key=focus_key,
            path=path,
            source_shape=source_shape,
            component=component,
            focus_key_properties=focus_key_properties,
            targeted=memb_b["targeted"],
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
        ),
        "residual_results": _residuals_and_new(
            baseline_results, after_validation["results"], designated
        ),
    }


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
    try:
        designated_row = select_designated(
            baseline["results"],
            focus_key=focus_key,
            path=cfg.path,
            source_shape=cfg.source_shape,
            component=cfg.component,
            severity=cfg.severity,
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
            )
        else:
            raise

    designated = _signature(
        focus_key=focus_key,
        path=cfg.path,
        source_shape=cfg.source_shape,
        component=cfg.component,
        severity=cfg.severity,
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
                "as specified; not general domain correctness or full profile compliance."
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

    noop_warnings = []
    if data_diff.get("unchanged") is True:
        noop_warnings.append("data_repair_is_noop_relative_to_baseline_data")
    if shapes_diff.get("unchanged") is True:
        noop_warnings.append("constraint_revision_is_noop_relative_to_baseline_shapes")

    parents = find_parent_node_shapes(s0, URIRef(cfg.source_shape))

    return {
        "meta": {
            "tool": "shacl-compare",
            "version": __version__,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version.split()[0],
            "rdflib_version": __import__("rdflib").__version__,
            "validator": validator_meta(),
            "diff_iso_size_bound": MAX_TRIPLES_FOR_ISO,
            "interface": {
                "A_validates_with": "S0",
                "B_validates_with": "G0",
                "note": (
                    "Four-file interface fixes shapes for A and data for B; "
                    "this is not an independent off-interface purity audit."
                ),
            },
        },
        "inputs": {
            "data_baseline": str(cfg.data_baseline),
            "shapes_baseline": str(cfg.shapes_baseline),
            "data_repair": str(cfg.data_repair),
            "shapes_revision": str(cfg.shapes_revision),
            "requirement_card": (
                str(cfg.requirement_card) if cfg.requirement_card else None
            ),
        },
        "designated": {
            **designated,
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
