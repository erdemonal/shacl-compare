import json
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.cli import main

FIX = Path(__file__).parent / "fixtures" / "sensor_datatype"


def test_independent_datatype_case_not_person_firstname(tmp_path: Path):
    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(FIX / "G0.ttl"),
            "--shapes-baseline",
            str(FIX / "S0.ttl"),
            "--data-repair",
            str(FIX / "GA.ttl"),
            "--shapes-revision",
            str(FIX / "SB.ttl"),
            "--focus",
            "http://example.org/iot#SensorA",
            "--path",
            "http://example.org/iot#reading",
            "--source-shape",
            "http://example.org/iot#SensorShape-reading",
            "--component",
            str(SH.DatatypeConstraintComponent),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert report["intervention_A"]["target_membership"] == "RETAINED"
    assert report["data_diff"]["diff_status"] == "RESOLVED"
    assert report["meta"]["diff_iso_size_bound"]["role"] == (
        "provisional_performance_safeguard"
    )
    assert report["meta"]["diff_iso_size_bound"]["not_a_benchmarked_threshold"] is True
    assert "supported_scope_note" in report["meta"]


def test_sparql_shapes_flagged_in_undetermined(tmp_path: Path):
    shapes = tmp_path / "sparql_shapes.ttl"
    shapes.write_text(
        """
        @prefix ex: <http://example.org/iot#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:SensorShape a sh:NodeShape ;
          sh:targetClass ex:Sensor ;
          sh:property ex:SensorShape-reading ;
          sh:sparql [ sh:select "SELECT $this WHERE { $this a ex:Sensor }" ] .
        ex:SensorShape-reading a sh:PropertyShape ;
          sh:path ex:reading ;
          sh:datatype xsd:decimal ;
          sh:minCount 1 .
        """
    )
    out = tmp_path / "report.json"
    rc = main(
        [
            "--data-baseline",
            str(FIX / "G0.ttl"),
            "--shapes-baseline",
            str(shapes),
            "--data-repair",
            str(FIX / "GA.ttl"),
            "--shapes-revision",
            str(FIX / "SB.ttl"),
            "--focus",
            "http://example.org/iot#SensorA",
            "--path",
            "http://example.org/iot#reading",
            "--source-shape",
            "http://example.org/iot#SensorShape-reading",
            "--component",
            str(SH.DatatypeConstraintComponent),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert "shapes_contain_sh_sparql_baseline" in report["undetermined"]
