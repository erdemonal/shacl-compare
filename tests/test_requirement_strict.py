import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SH, XSD

from shacl_compare.requirements import (
    assess_cardinality_condition,
    load_requirement_card,
)


EX = URIRef("http://example.org/ns#")


def test_rejects_negative_expected_value(tmp_path: Path):
    card = tmp_path / "card.json"
    card.write_text(
        json.dumps(
            {
                "shape": str(EX + "P"),
                "path": str(EX + "firstName"),
                "parameter": "sh:maxCount",
                "expected_value": -1,
            }
        )
    )
    with pytest.raises(ValueError, match="non-negative"):
        load_requirement_card(card)


def test_rejects_bool_expected_value(tmp_path: Path):
    card = tmp_path / "card.json"
    card.write_text(
        json.dumps(
            {
                "shape": str(EX + "P"),
                "path": str(EX + "firstName"),
                "parameter": "sh:maxCount",
                "expected_value": True,
            }
        )
    )
    with pytest.raises(ValueError):
        load_requirement_card(card)


def test_no_path_on_shape_without_unique_property_is_not_held():
    shapes = Graph()
    node = EX + "PersonShape"
    shapes.add((node, RDF.type, SH.NodeShape))
    shapes.add((node, SH.minCount, Literal(1)))  # wrong place on purpose
    card = {
        "shape": str(node),
        "path": str(EX + "firstName"),
        "parameter": "sh:minCount",
        "parameter_iri": str(SH.minCount),
        "expected_value": 1,
    }
    result = assess_cardinality_condition(shapes, card)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["status"] != "CONDITION_HELD"


def test_property_shape_path_must_match():
    shapes = Graph()
    prop = EX + "P"
    shapes.add((prop, SH.path, EX + "lastName"))
    shapes.add((prop, SH.maxCount, Literal(1)))
    card = {
        "shape": str(prop),
        "path": str(EX + "firstName"),
        "parameter": "sh:maxCount",
        "parameter_iri": str(SH.maxCount),
        "expected_value": 1,
    }
    result = assess_cardinality_condition(shapes, card)
    assert result["status"] == "NOT_COMPARABLE"
