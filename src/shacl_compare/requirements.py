from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import SH


SUPPORTED_PARAMETERS = {
    str(SH.minCount): SH.minCount,
    str(SH.maxCount): SH.maxCount,
    "sh:minCount": SH.minCount,
    "sh:maxCount": SH.maxCount,
}


def load_requirement_card(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("requirement card must be a JSON object")
    required = ("shape", "path", "parameter", "expected_value")
    for key in required:
        if key not in data:
            raise ValueError(f"requirement card missing field: {key}")
    param = str(data["parameter"])
    if param not in SUPPORTED_PARAMETERS:
        raise ValueError(
            f"unsupported requirement parameter {param!r}; "
            f"v0.1 supports only sh:minCount and sh:maxCount"
        )
    try:
        expected = int(data["expected_value"])
    except (TypeError, ValueError) as exc:
        raise ValueError("expected_value must be an integer") from exc
    return {
        "shape": str(data["shape"]),
        "path": str(data["path"]),
        "parameter": param,
        "parameter_iri": str(SUPPORTED_PARAMETERS[param]),
        "expected_value": expected,
        "citation": data.get("citation"),
    }


def assess_cardinality_condition(
    shapes: Graph,
    card: dict[str, Any],
) -> dict[str, Any]:
    """Report only whether the named shape still carries the expected cardinality parameter."""
    shape = URIRef(card["shape"])
    path = card["path"]
    param = URIRef(card["parameter_iri"])
    expected = card["expected_value"]

    # Confirm shape has this path (property shape itself or node shape→property).
    paths_on_shape = {str(p) for p in shapes.objects(shape, SH.path)}
    if paths_on_shape and path not in paths_on_shape:
        # Maybe card.shape is a node shape; find property shapes with path.
        prop_shapes = [
            ps
            for ps in shapes.objects(shape, SH.property)
            if path in {str(p) for p in shapes.objects(ps, SH.path)}
        ]
        if len(prop_shapes) != 1:
            return {
                "status": "NOT_COMPARABLE",
                "reason": "could_not_resolve_unique_property_shape_for_path",
                "check": "named_cardinality_condition",
            }
        shape = prop_shapes[0]

    values = sorted(str(v) for v in shapes.objects(shape, param))
    base = {
        "check": "named_cardinality_condition",
        "shape": str(shape),
        "path": path,
        "parameter": card["parameter_iri"],
        "expected_value": expected,
        "observed_values": values,
        "citation": card.get("citation"),
    }
    if not values:
        return {**base, "status": "CONDITION_ABSENT"}
    if len(values) == 1 and int(values[0]) == expected:
        return {**base, "status": "CONDITION_HELD"}
    return {**base, "status": "CONDITION_DIFFERENT"}
