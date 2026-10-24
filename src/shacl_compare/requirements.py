from __future__ import annotations

import json
import re
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

_NONNEG_INT = re.compile(r"^(0|[1-9][0-9]*)$")


def _parse_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("expected_value must be a non-negative integer, not boolean")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("expected_value must be a non-negative integer")
        return value
    if isinstance(value, str) and _NONNEG_INT.fullmatch(value.strip()):
        return int(value.strip())
    raise ValueError("expected_value must be a non-negative integer")


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
            f"unsupported requirement parameter {param!r}. "
            f"v0.1 supports only sh:minCount and sh:maxCount"
        )
    expected = _parse_non_negative_int(data["expected_value"])
    return {
        "shape": str(data["shape"]),
        "path": str(data["path"]),
        "parameter": param,
        "parameter_iri": str(SUPPORTED_PARAMETERS[param]),
        "expected_value": expected,
        "citation": data.get("citation"),
    }


def _resolve_property_shape(
    shapes: Graph, shape: URIRef, path: str
) -> tuple[URIRef | None, str | None]:
    paths_on_shape = {str(p) for p in shapes.objects(shape, SH.path)}
    if path in paths_on_shape:
        return shape, None
    if paths_on_shape:
        return None, "shape_path_does_not_match_requirement_path"
    prop_shapes = [
        ps
        for ps in shapes.objects(shape, SH.property)
        if path in {str(p) for p in shapes.objects(ps, SH.path)}
    ]
    if len(prop_shapes) == 1:
        return prop_shapes[0], None  # type: ignore[return-value]
    if len(prop_shapes) == 0:
        return None, "could_not_resolve_property_shape_for_path"
    return None, "multiple_property_shapes_for_path"


def assess_cardinality_condition(
    shapes: Graph,
    card: dict[str, Any],
) -> dict[str, Any]:
    shape = URIRef(card["shape"])
    path = card["path"]
    param = URIRef(card["parameter_iri"])
    expected = card["expected_value"]

    resolved, reason = _resolve_property_shape(shapes, shape, path)
    base: dict[str, Any] = {
        "check": "named_cardinality_condition",
        "shape": str(shape),
        "path": path,
        "parameter": card["parameter_iri"],
        "expected_value": expected,
        "citation": card.get("citation"),
        "observed_values": [],
    }
    if resolved is None:
        return {**base, "status": "NOT_COMPARABLE", "reason": reason}

    values = sorted(str(v) for v in shapes.objects(resolved, param))
    base["shape"] = str(resolved)
    base["observed_values"] = values
    if not values:
        return {**base, "status": "CONDITION_ABSENT"}
    if len(values) == 1 and int(values[0]) == expected:
        return {**base, "status": "CONDITION_HELD"}
    return {**base, "status": "CONDITION_DIFFERENT"}
