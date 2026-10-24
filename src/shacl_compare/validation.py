from __future__ import annotations

from typing import Any

from rdflib import Graph
from rdflib.namespace import RDF, SH

from shacl_compare.custom_constraint_components import (
    annotate_results_with_custom_cc_fingerprints,
)
from shacl_compare.paths import annotate_results_with_path_fingerprints
from shacl_compare.sparql_constraints import annotate_results_with_sparql_fingerprints
from shacl_compare.terms import node_focus_key

try:
    import pyshacl
    from pyshacl import validate
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pyshacl is required") from exc


VALIDATE_KWARGS = {
    "inference": "none",
    "abort_on_first": False,
    "advanced": False,
}


def validator_meta() -> dict[str, Any]:
    return {
        "name": "pyshacl",
        "version": getattr(pyshacl, "__version__", "unknown"),
        **VALIDATE_KWARGS,
    }


def extract_results(
    report_graph: Graph,
    data_graph: Graph,
    focus_key_properties: list,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        row: dict[str, Any] = {}
        focus_nodes = list(report_graph.objects(result, SH.focusNode))
        if focus_nodes:
            focus = focus_nodes[0]
            row["focus_node"] = str(focus)
            row["focus_key"] = node_focus_key(data_graph, focus, focus_key_properties)
        for pred, key in (
            (SH.resultPath, "result_path"),
            (SH.sourceShape, "source_shape"),
            (SH.sourceConstraint, "source_constraint"),
            (SH.sourceConstraintComponent, "source_constraint_component"),
            (SH.resultSeverity, "severity"),
            (SH.value, "value"),
            (SH.resultMessage, "message"),
        ):
            vals = sorted({str(o) for o in report_graph.objects(result, pred)})
            if vals:
                row[key] = vals[0] if len(vals) == 1 else vals
        results.append(row)
    results.sort(
        key=lambda r: (
            r.get("focus_key", r.get("focus_node", "")),
            r.get("source_constraint_component", ""),
            r.get("result_path", ""),
            r.get("source_shape", ""),
        )
    )
    return results


def run_validation(
    data: Graph,
    shapes: Graph,
    focus_key_properties: list,
) -> dict[str, Any]:
    conforms, report_graph, text = validate(
        data,
        shacl_graph=shapes,
        **VALIDATE_KWARGS,
    )
    results = extract_results(report_graph, data, focus_key_properties)
    results = annotate_results_with_path_fingerprints(results, shapes)
    results = annotate_results_with_sparql_fingerprints(results, shapes)
    results = annotate_results_with_custom_cc_fingerprints(results, shapes)
    return {
        "conforms": bool(conforms),
        "results": results,
        "result_count": len(results),
        "human_text": text.strip() if isinstance(text, str) else str(text),
    }
