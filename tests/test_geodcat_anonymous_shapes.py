
from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SH, XSD

from shacl_compare.cli import main

GEO = Path("/tmp/GeoDCAT-AP/releases/2.0.0")
SHAPES = GEO / "geodcat-ap.shacl.ttl"
EXAMPLE = GEO / "examples" / "dataset.ttl"

FOCUS = (
    "https://some.catalogue/resource/"
    "eea_r_3035_10_m_noise-contours-end2017_i_2016_v01_r00"
)
CREATED = "http://purl.org/dc/terms/created"
COMP = str(SH.MaxCountConstraintComponent)

@pytest.mark.skipif(
    not SHAPES.is_file() or not EXAMPLE.is_file(),
    reason="GeoDCAT-AP 2.0.0 checkout not available under /tmp/GeoDCAT-AP",
)
def test_geodcat_original_shapes_without_skolem(tmp_path: Path):
    g0 = Graph()
    g0.parse(EXAMPLE)
    focus = URIRef(FOCUS)
    created = URIRef(CREATED)
    extra = Literal("2020-01-01", datatype=XSD.date)
    g0.add((focus, created, extra))
    g0_path = tmp_path / "G0.ttl"
    g0.serialize(g0_path, format="turtle")

    ga = Graph()
    ga.parse(EXAMPLE)
    ga_path = tmp_path / "GA.ttl"
    ga.serialize(ga_path, format="turtle")

    s0 = Graph()
    s0.parse(SHAPES)
    ds = URIRef("http://data.europa.eu/r5r#Dataset_Shape")
    ps = None
    for cand in s0.objects(ds, SH.property):
        if created in set(s0.objects(cand, SH.path)):
            ps = cand
            break
    assert ps is not None
    sb = Graph()
    sb += s0
    old = list(sb.objects(ps, SH.maxCount))
    assert len(old) == 1
    sb.remove((ps, SH.maxCount, old[0]))
    sb.add((ps, SH.maxCount, Literal(2)))
    sb_path = tmp_path / "SB.ttl"
    s0_path = tmp_path / "S0.ttl"
    s0.serialize(s0_path, format="turtle")
    sb.serialize(sb_path, format="turtle")

    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(g0_path),
            "--shapes-baseline",
            str(s0_path),
            "--data-repair",
            str(ga_path),
            "--shapes-revision",
            str(sb_path),
            "--focus",
            FOCUS,
            "--path",
            CREATED,
            "--component",
            COMP,
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["designated"]["source_shape_is_absolute_iri"] is False
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["target_membership"] == "RETAINED"
    assert report["intervention_B"]["target_membership"] == "RETAINED"
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )
