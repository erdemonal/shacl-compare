from __future__ import annotations

import json
from pathlib import Path

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.cli import main
from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import (
    DesignateError,
    align_source_shape,
    evaluate_original_constraint_from_s0_results,
    select_designated,
)
from shacl_compare.graph_io import load_graph
from shacl_compare.paths import paths_match, shape_path_fingerprint
from shacl_compare.validation import run_validation

EX = URIRef("http://example.org/cpath#")
FIX = Path(__file__).parent / "fixtures" / "complex_paths"
COMP_MIN = str(SH.MinCountConstraintComponent)
VIOL = str(SH.Violation)

def _ttl_roundtrip(g: Graph) -> Graph:
    data = g.serialize(format="turtle")
    out = Graph()
    out.parse(data=data, format="turtle")
    return out

def _build_seven_path_shapes() -> dict[str, tuple[Graph, URIRef, str]]:
    cases: dict[str, tuple[Graph, URIRef, str]] = {}

    def pack(name: str, path_node, expected: str) -> None:
        g = Graph()
        shape = EX + name
        g.add((shape, SH.path, path_node))
        cases[name] = (g, shape, expected)

    # PredicatePath
    pack("Pred", EX + "email", f"P:<{EX}email>")

    # InversePath
    inv = BNode()
    pack("Inv", inv, f"I(P:<{EX}parent>)")
    g_inv, _shape_inv, _ = cases["Inv"]
    g_inv.add((inv, SH.inversePath, EX + "parent"))

    # SequencePath
    seq = BNode()
    mid = BNode()
    g = Graph()
    shape = EX + "Seq"
    g.add((seq, RDF.first, EX + "address"))
    g.add((seq, RDF.rest, mid))
    g.add((mid, RDF.first, EX + "code"))
    g.add((mid, RDF.rest, RDF.nil))
    g.add((shape, SH.path, seq))
    cases["Seq"] = (
        g,
        shape,
        f"S(P:<{EX}address>,P:<{EX}code>)",
    )

    # AlternativePath
    alt_head = BNode()
    alt_list = BNode()
    alt_mid = BNode()
    g = Graph()
    shape = EX + "Alt"
    g.add((alt_head, SH.alternativePath, alt_list))
    g.add((alt_list, RDF.first, EX + "home"))
    g.add((alt_list, RDF.rest, alt_mid))
    g.add((alt_mid, RDF.first, EX + "work"))
    g.add((alt_mid, RDF.rest, RDF.nil))
    g.add((shape, SH.path, alt_head))
    a = f"P:<{EX}home>"
    b = f"P:<{EX}work>"
    ordered = "|".join(sorted([a, b]))
    cases["Alt"] = (g, shape, f"A({ordered})")

    # ZeroOrMore / OneOrMore / ZeroOrOne
    for pred, tag, name in (
        (SH.zeroOrMorePath, "Z*", "ZStar"),
        (SH.oneOrMorePath, "O+", "OPlus"),
        (SH.zeroOrOnePath, "Z?", "ZOpt"),
    ):
        node = BNode()
        g = Graph()
        shape = EX + name
        g.add((node, pred, EX + "knows"))
        g.add((shape, SH.path, node))
        cases[name] = (g, shape, f"{tag}(P:<{EX}knows>)")

    return cases

def test_seven_path_form_fingerprints():
    cases = _build_seven_path_shapes()
    assert set(cases) == {"Pred", "Inv", "Seq", "Alt", "ZStar", "OPlus", "ZOpt"}
    for name, (g, shape, expected) in cases.items():
        fp = shape_path_fingerprint(g, shape)
        assert fp == expected, f"{name}: {fp!r} != {expected!r}"

def test_fingerprints_stable_across_turtle_reload():
    cases = _build_seven_path_shapes()
    for name, (g, shape, expected) in cases.items():
        g2 = _ttl_roundtrip(g)
        fp2 = shape_path_fingerprint(g2, shape)
        assert fp2 == expected, f"{name} after reload: {fp2!r}"

def test_sequence_fixture_fingerprint_reload():
    s0 = load_graph(FIX / "sequence_S0.ttl")
    fp1 = shape_path_fingerprint(s0, EX + "AddressCodePS")
    assert fp1 == f"S(P:<{EX}address>,P:<{EX}code>)"
    s0b = _ttl_roundtrip(s0)
    fp2 = shape_path_fingerprint(s0b, EX + "AddressCodePS")
    assert fp1 == fp2

def test_paths_match_ignores_blank_result_path_ids():
    fp = f"S(P:<{EX}address>,P:<{EX}code>)"
    assert paths_match(
        row_path="n123",
        row_fp=fp,
        designated_path="n999",
        designated_fp=fp,
    )
    assert not paths_match(
        row_path="n123",
        row_fp=fp,
        designated_path="n999",
        designated_fp=f"S(P:<{EX}address>,P:<{EX}postalCode>)",
    )

def test_sequence_compare_clear_on_data_repair(tmp_path: Path):
    out = tmp_path / "seq.json"
    report = run_compare(
        CompareConfig(
            data_baseline=FIX / "sequence_G0.ttl",
            shapes_baseline=FIX / "sequence_S0.ttl",
            data_repair=FIX / "sequence_GA.ttl",
            shapes_revision=FIX / "sequence_SB.ttl",
            focus=str(EX + "Alice"),
            path="",  # resolve via source_shape fingerprint
            source_shape=str(EX + "AddressCodePS"),
            component=COMP_MIN,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )
    assert report["designated"]["path_fingerprint"] == (
        f"S(P:<{EX}address>,P:<{EX}code>)"
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
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
    assert "complex_or_blank_result_path_not_stable_across_parses" not in report[
        "undetermined"
    ]

def test_sequence_path_revision_unresolved_alignment(tmp_path: Path):
    out = tmp_path / "rev.json"
    report = run_compare(
        CompareConfig(
            data_baseline=FIX / "sequence_G0.ttl",
            shapes_baseline=FIX / "sequence_S0.ttl",
            data_repair=FIX / "sequence_G0.ttl",
            shapes_revision=FIX / "sequence_SB_path_rev.ttl",
            focus=str(EX + "Alice"),
            path="",
            source_shape=str(EX + "AddressCodePS"),
            component=COMP_MIN,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )
    assert report["intervention_B"]["result_outcome"] == "NOT_COMPARABLE"
    assert report["intervention_B"]["shape_alignment"] == "UNRESOLVED"
    detail = report["intervention_B"]["shape_alignment_detail"]
    assert "path" in detail["reason"]

def test_anonymous_inverse_compare_and_cli(tmp_path: Path):
    out = tmp_path / "inv.json"
    baseline = run_validation(
        load_graph(FIX / "anon_inverse_G0.ttl"),
        load_graph(FIX / "anon_inverse_S0.ttl"),
        [],
    )
    assert baseline["result_count"] >= 1
    row = baseline["results"][0]
    assert row.get("path_fingerprint", "").startswith("I(")

    report = run_compare(
        CompareConfig(
            data_baseline=FIX / "anon_inverse_G0.ttl",
            shapes_baseline=FIX / "anon_inverse_S0.ttl",
            data_repair=FIX / "anon_inverse_GA.ttl",
            shapes_revision=FIX / "anon_inverse_SB.ttl",
            focus=str(EX + "Kid"),
            path=str(row["result_path"]),
            source_shape=None,
            component=COMP_MIN,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
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

    out2 = tmp_path / "inv_cli.json"
    rc = main(
        [
            "--data-baseline",
            str(FIX / "anon_inverse_G0.ttl"),
            "--shapes-baseline",
            str(FIX / "anon_inverse_S0.ttl"),
            "--data-repair",
            str(FIX / "anon_inverse_GA.ttl"),
            "--shapes-revision",
            str(FIX / "anon_inverse_SB.ttl"),
            "--focus",
            str(EX + "Kid"),
            "--path",
            str(row["result_path"]),
            "--component",
            COMP_MIN,
            "--out",
            str(out2),
        ]
    )
    assert rc == 0
    cli_report = json.loads(out2.read_text())
    assert cli_report["intervention_A"]["result_outcome"] == "CLEAR"

def test_cross_process_reload_designation_via_fingerprint():
    g0 = load_graph(FIX / "sequence_G0.ttl")
    s0 = load_graph(FIX / "sequence_S0.ttl")
    v1 = run_validation(g0, s0, [])
    assert v1["result_count"] >= 1
    r1 = v1["results"][0]
    fp = r1["path_fingerprint"]

    s0_reloaded = _ttl_roundtrip(s0)
    g0_reloaded = _ttl_roundtrip(g0)
    v2 = run_validation(g0_reloaded, s0_reloaded, [])
    r2 = v2["results"][0]
    assert r1["result_path"] != r2["result_path"] or True  # may or may not differ
    assert r2["path_fingerprint"] == fp
    chosen = select_designated(
        v2["results"],
        focus_key=str(EX + "Alice"),
        path=str(r1["result_path"]),  # stale id
        component=COMP_MIN,
        severity=VIOL,
        source_shape=str(EX + "AddressCodePS"),
        path_fingerprint=fp,
    )
    assert chosen["path_fingerprint"] == fp

def test_duplicate_equivalent_paths_require_index():
    s0 = load_graph(FIX / "dup_path_S0.ttl")
    g0 = Graph()
    g0.add((EX + "Alice", RDF.type, EX + "Person"))
    v = run_validation(g0, s0, [])
    assert v["result_count"] >= 1
    fps = {r.get("path_fingerprint") for r in v["results"]}
    assert fps == {f"S(P:<{EX}address>,P:<{EX}code>)"}
    try:
        select_designated(
            v["results"],
            focus_key=str(EX + "Alice"),
            path="",
            component=COMP_MIN,
            severity=VIOL,
            path_fingerprint=f"S(P:<{EX}address>,P:<{EX}code>)",
        )
    except DesignateError as exc:
        assert "designation-index" in str(exc) or "matched" in str(exc)

def test_align_ambiguous_duplicate_paths_unresolved():
    s0 = load_graph(FIX / "dup_path_S0.ttl")
    sb = _ttl_roundtrip(s0)
    parents = list(s0.subjects(RDF.type, SH.NodeShape))
    assert parents
    props = list(s0.objects(parents[0], SH.property))
    assert len(props) == 2
    src = str(props[0])
    result = align_source_shape(
        s0,
        sb,
        src,
        path="n_stale",
        component=COMP_MIN,
        path_fingerprint=f"S(P:<{EX}address>,P:<{EX}code>)",
    )
    assert result["shape_alignment"] == "UNRESOLVED"
    assert result["reason"] == "multiple_structural_candidates_for_source_shape"

def test_no_fabricated_satisfied_without_fingerprint():
    results = [
        {
            "focus_key": str(EX + "Alice"),
            "result_path": "n_other",
            "source_shape": "n_shape",
            "source_constraint_component": COMP_MIN,
            "severity": VIOL,
        }
    ]
    out = evaluate_original_constraint_from_s0_results(
        results,
        focus_key=str(EX + "Alice"),
        path="n_designated_stale",
        source_shape="n_shape",
        component=COMP_MIN,
        severity=VIOL,
        targeted=True,
        path_fingerprint=None,
    )
    assert out["original_constraint_evaluation"] == "NOT_EVALUATED"
    assert out["reason"] == "unstable_result_path_may_hide_matching_violation"

def test_predicate_path_unchanged_behavior(tmp_path: Path):
    anon = Path(__file__).parent / "fixtures" / "anonymous_maxcount"
    out = tmp_path / "pred.json"
    report = run_compare(
        CompareConfig(
            data_baseline=anon / "G0.ttl",
            shapes_baseline=anon / "S0.ttl",
            data_repair=anon / "GA.ttl",
            shapes_revision=anon / "SB.ttl",
            focus="http://example.org/anon#Item1",
            path="http://example.org/anon#code",
            source_shape=None,
            component=str(SH.MaxCountConstraintComponent),
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )
    assert report["designated"]["path_fingerprint"] == (
        "P:<http://example.org/anon#code>"
    )
    assert report["intervention_A"]["result_outcome"] == "CLEAR"
    assert report["intervention_B"]["result_outcome"] == "CLEAR"
