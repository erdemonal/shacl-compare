
from __future__ import annotations

from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import (
    DesignateError,
    align_source_shape,
    evaluate_original_constraint_from_s0_results,
    select_designated,
)
from shacl_compare.graph_io import load_graph
from shacl_compare.paths import shape_path_fingerprint
from shacl_compare.validation import run_validation

EX = URIRef("http://example.org/cpath#")
FIX = Path(__file__).parent / "fixtures" / "complex_paths"
COMP_MIN = str(SH.MinCountConstraintComponent)
VIOL = str(SH.Violation)

FORMS = {
    "Z*": {
        "prefix": "zstar",
        "shape": EX + "KnowsStarPS",
        "fp": f"Z*(P:<{EX}knows>)",
    },
    "O+": {
        "prefix": "oplus",
        "shape": EX + "KnowsPlusPS",
        "fp": f"O+(P:<{EX}knows>)",
    },
    "Z?": {
        "prefix": "zopt",
        "shape": EX + "KnowsOptPS",
        "fp": f"Z?(P:<{EX}knows>)",
    },
}

def _ttl_roundtrip(g: Graph) -> Graph:
    data = g.serialize(format="turtle")
    out = Graph()
    out.parse(data=data, format="turtle")
    return out

def _run(
    prefix: str,
    *,
    out: Path,
    shapes_revision: str | None = None,
    data_repair: str | None = None,
    source_shape: str | None = None,
    path: str = "",
) -> dict:
    meta = next(v for v in FORMS.values() if v["prefix"] == prefix)
    return run_compare(
        CompareConfig(
            data_baseline=FIX / f"{prefix}_G0.ttl",
            shapes_baseline=FIX / f"{prefix}_S0.ttl",
            data_repair=FIX / (data_repair or f"{prefix}_GA.ttl"),
            shapes_revision=FIX
            / (shapes_revision or f"{prefix}_SB.ttl"),
            focus=str(EX + "Alice"),
            path=path,
            source_shape=source_shape if source_shape is not None else str(meta["shape"]),
            component=COMP_MIN,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=out,
        )
    )

def test_fingerprint_fixtures_match_expected_tags():
    for tag, meta in FORMS.items():
        s0 = load_graph(FIX / f"{meta['prefix']}_S0.ttl")
        fp = shape_path_fingerprint(s0, meta["shape"])
        assert fp == meta["fp"], tag

def test_each_form_clear_with_fingerprint_and_other_focus(tmp_path: Path):
    for tag, meta in FORMS.items():
        base = run_validation(
            load_graph(FIX / f"{meta['prefix']}_G0.ttl"),
            load_graph(FIX / f"{meta['prefix']}_S0.ttl"),
            [],
        )
        assert base["conforms"] is False, tag
        assert all(
            r.get("path_fingerprint") == meta["fp"] for r in base["results"]
        ), tag
        assert any(r["focus_key"] == str(EX + "Alice") for r in base["results"]), tag
        assert any(r["focus_key"] == str(EX + "Bob") for r in base["results"]), tag

        a_ok = run_validation(
            load_graph(FIX / f"{meta['prefix']}_GA.ttl"),
            load_graph(FIX / f"{meta['prefix']}_S0.ttl"),
            [],
        )
        alice_a = [
            r for r in a_ok["results"] if r["focus_key"] == str(EX + "Alice")
        ]
        bob_a = [r for r in a_ok["results"] if r["focus_key"] == str(EX + "Bob")]
        assert alice_a == [], tag
        assert bob_a, tag

        b_ok = run_validation(
            load_graph(FIX / f"{meta['prefix']}_G0.ttl"),
            load_graph(FIX / f"{meta['prefix']}_SB.ttl"),
            [],
        )
        assert b_ok["conforms"] is True, tag

        report = _run(meta["prefix"], out=tmp_path / f"{meta['prefix']}_clear.json")
        assert report["designated"]["path_fingerprint"] == meta["fp"], tag
        assert report["intervention_A"]["result_outcome"] == "CLEAR", tag
        assert report["intervention_B"]["result_outcome"] == "CLEAR", tag
        assert (
            report["intervention_A"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "SATISFIED"
        ), tag
        assert (
            report["intervention_B"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "VIOLATED"
        ), tag
        assert report["intervention_A"]["target_membership"] == "RETAINED", tag
        others = {
            o["focus_key"]: o["result_outcome"]
            for o in report["intervention_A"]["other_focus_nodes"]
        }
        assert others.get(str(EX + "Bob")) == "PERSIST", tag

def test_each_form_persist(tmp_path: Path):
    for tag, meta in FORMS.items():
        report = _run(
            meta["prefix"],
            out=tmp_path / f"{meta['prefix']}_persist.json",
            data_repair=f"{meta['prefix']}_G0.ttl",
            shapes_revision=f"{meta['prefix']}_S0.ttl",
        )
        assert report["intervention_A"]["result_outcome"] == "PERSIST", tag
        assert report["intervention_B"]["result_outcome"] == "PERSIST", tag
        assert (
            report["intervention_A"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "VIOLATED"
        ), tag
        assert (
            report["intervention_B"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "VIOLATED"
        ), tag

def test_each_form_path_revision_not_comparable(tmp_path: Path):
    for tag, meta in FORMS.items():
        report = _run(
            meta["prefix"],
            out=tmp_path / f"{meta['prefix']}_rev.json",
            data_repair=f"{meta['prefix']}_G0.ttl",
            shapes_revision=f"{meta['prefix']}_SB_path_rev.ttl",
        )
        assert report["intervention_B"]["result_outcome"] == "NOT_COMPARABLE", tag
        assert report["intervention_B"]["shape_alignment"] == "UNRESOLVED", tag
        reason = report["intervention_B"]["shape_alignment_detail"]["reason"]
        assert "path" in reason, (tag, reason)
        assert (
            report["intervention_B"]["original_constraint_evaluation"][
                "original_constraint_evaluation"
            ]
            == "VIOLATED"
        ), tag

def test_anonymous_zero_or_one_compare(tmp_path: Path):
    base = run_validation(
        load_graph(FIX / "anon_zopt_G0.ttl"),
        load_graph(FIX / "anon_zopt_S0.ttl"),
        [],
    )
    assert base["result_count"] >= 1
    row = base["results"][0]
    assert row["path_fingerprint"] == f"Z?(P:<{EX}knows>)"

    report = run_compare(
        CompareConfig(
            data_baseline=FIX / "anon_zopt_G0.ttl",
            shapes_baseline=FIX / "anon_zopt_S0.ttl",
            data_repair=FIX / "anon_zopt_GA.ttl",
            shapes_revision=FIX / "anon_zopt_SB.ttl",
            focus=str(EX + "Alice"),
            path=str(row["result_path"]),
            source_shape=None,
            component=COMP_MIN,
            severity=VIOL,
            focus_key_properties=[],
            requirement_card=None,
            out=tmp_path / "anon_zopt.json",
        )
    )
    assert report["designated"]["path_fingerprint"] == f"Z?(P:<{EX}knows>)"
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

def test_reload_designation_via_fingerprint_for_zstar():
    g0 = load_graph(FIX / "zstar_G0.ttl")
    s0 = load_graph(FIX / "zstar_S0.ttl")
    v1 = run_validation(g0, s0, [])
    alice = next(r for r in v1["results"] if r["focus_key"] == str(EX + "Alice"))
    fp = alice["path_fingerprint"]
    assert fp == f"Z*(P:<{EX}knows>)"

    v2 = run_validation(_ttl_roundtrip(g0), _ttl_roundtrip(s0), [])
    alice2 = next(r for r in v2["results"] if r["focus_key"] == str(EX + "Alice"))
    assert alice2["path_fingerprint"] == fp

    chosen = select_designated(
        v2["results"],
        focus_key=str(EX + "Alice"),
        path=str(alice["result_path"]),  # possibly stale blank id
        component=COMP_MIN,
        severity=VIOL,
        source_shape=str(EX + "KnowsStarPS"),
        path_fingerprint=fp,
    )
    assert chosen["path_fingerprint"] == fp

def test_duplicate_zstar_paths_alignment_unresolved():
    s0 = load_graph(FIX / "dup_zstar_S0.ttl")
    g0 = Graph()
    g0.add((EX + "Alice", RDF.type, EX + "Person"))
    v = run_validation(g0, s0, [])
    assert v["result_count"] >= 2
    fps = {r.get("path_fingerprint") for r in v["results"]}
    assert fps == {f"Z*(P:<{EX}knows>)"}

    try:
        select_designated(
            v["results"],
            focus_key=str(EX + "Alice"),
            path="",
            component=COMP_MIN,
            severity=VIOL,
            path_fingerprint=f"Z*(P:<{EX}knows>)",
        )
        raise AssertionError("expected DesignateError for duplicate Z* paths")
    except DesignateError as exc:
        assert "designation-index" in str(exc) or "matched" in str(exc)

    sb = _ttl_roundtrip(s0)
    props = list(s0.objects(EX + "PersonShape", SH.property))
    assert len(props) == 2
    result = align_source_shape(
        s0,
        sb,
        str(props[0]),
        path="n_stale",
        component=COMP_MIN,
        path_fingerprint=f"Z*(P:<{EX}knows>)",
    )
    assert result["shape_alignment"] == "UNRESOLVED"
    assert result["reason"] == "multiple_structural_candidates_for_source_shape"

def test_no_fabricated_satisfied_for_zstar_without_fingerprint():
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

def test_depth_semantics_distinguish_forms():
    g = Graph()
    g.parse(
        data=f"""
@prefix ex: <{EX}> .
ex:Alice a ex:Person ; ex:knows ex:Bob .
ex:Bob a ex:Person ; ex:knows ex:Carol .
ex:Carol a ex:Person .
""",
        format="turtle",
    )

    def conforms(path_ttl: str, min_count: int) -> bool:
        s = Graph()
        s.parse(
            data=f"""
@prefix ex: <{EX}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetNode ex:Alice ; sh:property [
  sh:path {path_ttl} ; sh:minCount {min_count}
] .
""",
            format="turtle",
        )
        return run_validation(g, s, [])["conforms"]

    # Z*: Alice/Bob/Carol → minCount 3 ok
    assert conforms("[ sh:zeroOrMorePath ex:knows ]", 3) is True
    # O+: Bob/Carol → minCount 3 fails, minCount 2 ok
    assert conforms("[ sh:oneOrMorePath ex:knows ]", 3) is False
    assert conforms("[ sh:oneOrMorePath ex:knows ]", 2) is True
    # Z?: Alice/Bob → minCount 3 fails, minCount 2 ok
    assert conforms("[ sh:zeroOrOnePath ex:knows ]", 3) is False
    assert conforms("[ sh:zeroOrOnePath ex:knows ]", 2) is True
