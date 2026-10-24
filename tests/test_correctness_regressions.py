
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import (
    _component_parameter,
    align_source_shape,
    evaluate_original_cardinality_on_focus,
    original_cardinality_parameter,
)
from shacl_compare.graph_io import load_graph
from shacl_compare.validation import run_validation

EX = URIRef("http://example.org/corr#")

def test_qualified_min_count_not_mapped_to_min_count():
    qmin = str(SH.QualifiedMinCountConstraintComponent)
    qmax = str(SH.QualifiedMaxCountConstraintComponent)
    assert _component_parameter(qmin) is None
    assert _component_parameter(qmax) is None
    assert _component_parameter(str(SH.MinCountConstraintComponent)) == SH.minCount
    assert _component_parameter(str(SH.MaxCountConstraintComponent)) == SH.maxCount

def test_qualified_original_eval_is_not_evaluated_even_with_mincount_collision():
    shapes = Graph()
    ps = EX + "P"
    shapes.add((ps, RDF.type, SH.PropertyShape))
    shapes.add((ps, SH.path, EX + "member"))
    shapes.add((ps, SH.minCount, Literal(1)))
    shapes.add((ps, SH.qualifiedMinCount, Literal(2)))

    param = original_cardinality_parameter(
        shapes, str(ps), str(SH.QualifiedMinCountConstraintComponent)
    )
    assert param is None

    result = evaluate_original_cardinality_on_focus(
        Graph(),
        shapes,
        focus_key=str(EX + "N"),
        path=str(EX + "member"),
        source_shape=str(ps),
        component=str(SH.QualifiedMinCountConstraintComponent),
        focus_key_properties=[],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "unsupported_component_for_original_evaluation"

def test_qualified_alignment_does_not_report_mincount_absent():
    base = Graph()
    parent = EX + "S"
    ps = EX + "S-m"
    base.add((parent, RDF.type, SH.NodeShape))
    base.add((parent, SH.property, ps))
    base.add((ps, RDF.type, SH.PropertyShape))
    base.add((ps, SH.path, EX + "member"))
    base.add((ps, SH.qualifiedMinCount, Literal(2)))
    base.add((ps, SH.qualifiedValueShape, BNode()))

    after = Graph()
    for t in base:
        after.add(t)

    result = align_source_shape(
        base,
        after,
        str(ps),
        str(EX + "member"),
        str(SH.QualifiedMinCountConstraintComponent),
    )
    assert result["shape_alignment"] == "ALIGNED"
    assert result.get("constraint_parameter_status") == "NOT_APPLICABLE"

def test_blank_result_path_never_yields_satisfied_original_eval():
    shapes = Graph()
    ps = EX + "S-e"
    shapes.add((ps, RDF.type, SH.PropertyShape))
    path_list = BNode()
    shapes.add((ps, SH.path, path_list))
    shapes.add((path_list, RDF.first, EX + "knows"))
    shapes.add((path_list, RDF.rest, RDF.nil))
    shapes.add((ps, SH.maxCount, Literal(1)))

    data = Graph()
    data.add((EX + "N", RDF.type, EX + "T"))
    fake_path = "n" + "a" * 32 + "b1"
    result = evaluate_original_cardinality_on_focus(
        data,
        shapes,
        focus_key=str(EX + "N"),
        path=fake_path,
        source_shape=str(ps),
        component=str(SH.MaxCountConstraintComponent),
        focus_key_properties=[],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "designated_path_not_iri_predicate_path"

def test_complex_shape_path_blocks_original_eval_even_with_iri_cli_path():
    shapes = Graph()
    ps = EX + "S-e"
    shapes.add((ps, RDF.type, SH.PropertyShape))
    path_list = BNode()
    shapes.add((ps, SH.path, path_list))
    shapes.add((path_list, RDF.first, EX + "knows"))
    shapes.add((path_list, RDF.rest, RDF.nil))
    shapes.add((ps, SH.maxCount, Literal(1)))

    result = evaluate_original_cardinality_on_focus(
        Graph(),
        shapes,
        focus_key=str(EX + "N"),
        path=str(EX + "knows"),  # IRI, but not the shape's PredicatePath
        source_shape=str(ps),
        component=str(SH.MaxCountConstraintComponent),
        focus_key_properties=[],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert result["reason"] == "shape_path_not_iri_predicate_path"

def test_complex_path_alignment_explicitly_unresolved(tmp_path: Path):
    s0 = tmp_path / "S0.ttl"
    sb = tmp_path / "SB.ttl"
    s0.write_text(
        """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:S-e .
ex:S-e a sh:PropertyShape ;
  sh:path ( ex:knows ex:email ) ;
  sh:maxCount 1 .
""".strip()
        + "\n"
    )
    sb.write_text(
        """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:S-e .
ex:S-e a sh:PropertyShape ;
  sh:path ( ex:knows ex:email ) ;
  sh:maxCount 2 .
""".strip()
        + "\n"
    )
    base = load_graph(s0)
    after = load_graph(sb)
    # Stale blank resultPath: align via structural fingerprint.
    result = align_source_shape(
        base,
        after,
        "http://example.org/cp#S-e",
        "n0123456789abcdef0123456789abcdefb1",
        str(SH.MaxCountConstraintComponent),
    )
    assert result["shape_alignment"] == "ALIGNED"
    assert "fingerprint" in result["reason"] or result["reason"].startswith("same_iri")
    assert result.get("path_fingerprint", "").startswith("S(")

def test_complex_path_compare_flags_limitation(tmp_path: Path):
    g0 = tmp_path / "G0.ttl"
    ga = tmp_path / "GA.ttl"
    s0 = tmp_path / "S0.ttl"
    sb = tmp_path / "SB.ttl"
    g0.write_text(
        "@prefix ex: <http://example.org/cp#> .\n"
        "ex:N a ex:T ; ex:knows ex:A . ex:A ex:email \"a@x\" , \"b@x\" .\n"
    )
    ga.write_text(
        "@prefix ex: <http://example.org/cp#> .\n"
        "ex:N a ex:T ; ex:knows ex:A . ex:A ex:email \"a@x\" .\n"
    )
    s0.write_text(
        """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:S-e .
ex:S-e a sh:PropertyShape ;
  sh:path ( ex:knows ex:email ) ;
  sh:maxCount 1 .
""".strip()
        + "\n"
    )
    sb.write_text(
        """
@prefix ex: <http://example.org/cp#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:S-e .
ex:S-e a sh:PropertyShape ;
  sh:path ( ex:knows ex:email ) ;
  sh:maxCount 2 .
""".strip()
        + "\n"
    )

    base = run_validation(load_graph(g0), load_graph(s0), [])
    assert base["results"]
    row = base["results"][0]
    stale_path = row["result_path"]
    assert not stale_path.startswith("http")

    # Stale blank resultPath must not block IRI source_shape designation.
    report = run_compare(
        CompareConfig(
            data_baseline=g0,
            shapes_baseline=s0,
            data_repair=ga,
            shapes_revision=sb,
            focus=row["focus_key"],
            path=stale_path,
            source_shape=row["source_shape"],
            component=row["source_constraint_component"],
            severity=row.get("severity") or str(SH.Violation),
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "out.json",
        )
    )
    assert report["designated"]["designation_mode"] in {
        "iri_source_shape",
        "iri_source_shape_path_fingerprint",
        "iri_source_shape_unstable_path_ignored",
    }
    assert report["designated"]["path_fingerprint"].startswith("S(")
    und = report["undetermined"]
    assert "designated_path_not_absolute_iri_predicate_path" in und
    assert "complex_or_blank_result_path_not_stable_across_parses" not in und
    assert "shapes_contain_non_iri_path_baseline" in und
    # Complex path: VR-filter via fingerprint. Cardinality cross-check stays NOT_EVALUATED.
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "SATISFIED"
    )
    assert (
        report["intervention_A"]["original_constraint_evaluation"]["method"]
        == "s0_validation_result_filter"
    )
    assert (
        report["intervention_A"]["original_constraint_evaluation"][
            "cardinality_crosscheck"
        ]["original_constraint_evaluation"]
        == "NOT_EVALUATED"
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["shape_alignment"] == "ALIGNED"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
    assert (
        report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ]
        == "VIOLATED"
    )

def test_node_level_empty_path_alignment_when_constraint_removed():
    base = Graph()
    node = EX + "S"
    base.add((node, RDF.type, SH.NodeShape))
    base.add((node, SH.targetNode, EX + "N"))
    forbidden = BNode()
    base.add((node, SH["not"], forbidden))
    base.add((forbidden, SH["class"], EX + "Forbidden"))

    after = Graph()
    after.add((node, RDF.type, SH.NodeShape))
    after.add((node, SH.targetNode, EX + "N"))

    result = align_source_shape(
        base, after, str(node), "", str(SH.NotConstraintComponent)
    )
    assert result["shape_alignment"] == "ALIGNED"
    assert result["reason"] == "same_iri_node_level_shape_no_property_path"
    assert result.get("constraint_parameter_status") == "NOT_APPLICABLE"

def test_node_level_compare_clear_only_after_justified_alignment(tmp_path: Path):
    g0 = tmp_path / "G0.ttl"
    ga = tmp_path / "GA.ttl"
    s0 = tmp_path / "S0.ttl"
    sb = tmp_path / "SB.ttl"
    g0.write_text("@prefix ex: <http://example.org/not#> .\nex:N a ex:Forbidden .\n")
    ga.write_text("@prefix ex: <http://example.org/not#> .\nex:N a ex:Allowed .\n")
    s0.write_text(
        """
@prefix ex: <http://example.org/not#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetNode ex:N ;
  sh:not [ sh:class ex:Forbidden ] .
""".strip()
        + "\n"
    )
    sb.write_text(
        """
@prefix ex: <http://example.org/not#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetNode ex:N .
""".strip()
        + "\n"
    )

    report = run_compare(
        CompareConfig(
            data_baseline=g0,
            shapes_baseline=s0,
            data_repair=ga,
            shapes_revision=sb,
            focus="http://example.org/not#N",
            path="",
            source_shape="http://example.org/not#S",
            component=str(SH.NotConstraintComponent),
            severity=str(SH.Violation),
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "out.json",
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["shape_alignment"] == "ALIGNED"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
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
    assert "designated_path_empty_node_level_or_missing_result_path" in report[
        "undetermined"
    ]

def test_iri_predicate_path_original_eval_still_works():
    shapes = Graph()
    ps = EX + "P"
    shapes.add((ps, RDF.type, SH.PropertyShape))
    shapes.add((ps, SH.path, EX + "v"))
    shapes.add((ps, SH.maxCount, Literal(1)))

    data = Graph()
    data.add((EX + "N", EX + "v", Literal("only")))

    result = evaluate_original_cardinality_on_focus(
        data,
        shapes,
        focus_key=str(EX + "N"),
        path=str(EX + "v"),
        source_shape=str(ps),
        component=str(SH.MaxCountConstraintComponent),
        focus_key_properties=[],
        targeted=True,
    )
    assert result["original_constraint_evaluation"] == "SATISFIED"
    assert result["observed_value_count"] == 1
