from __future__ import annotations

from typing import Any

from rdflib import Graph
from rdflib.compare import isomorphic

from shacl_compare.graph_io import graph_contains_blank_nodes
from shacl_compare.terms import serialize_triple, triple_key

# Soft bound: above this, blank-node pairs are not analysed further.
MAX_TRIPLES_FOR_ISO = 50_000


def diff_graphs(before: Graph, after: Graph) -> dict[str, Any]:
    """Compare two graphs under the v0.1 blank-node policy.

    Ground graphs: exact triple set difference (RESOLVED).
    Blank nodes present:
      - isomorphic → RESOLVED empty edit list (no structural change)
      - otherwise → AMBIGUOUS with no invented triple edit mapping
    """
    before_has_b = graph_contains_blank_nodes(before)
    after_has_b = graph_contains_blank_nodes(after)

    if not before_has_b and not after_has_b:
        return _ground_diff(before, after)

    n = len(before) + len(after)
    if n > MAX_TRIPLES_FOR_ISO:
        return {
            "diff_status": "AMBIGUOUS",
            "reason": "blank_nodes_present_and_graph_pair_exceeds_iso_size_bound",
            "size_bound": MAX_TRIPLES_FOR_ISO,
            "before_triple_count": len(before),
            "after_triple_count": len(after),
            "rdf_triple_deletions": [],
            "rdf_triple_additions": [],
            "deletion_count": None,
            "addition_count": None,
            "unchanged": None,
        }

    if isomorphic(before, after):
        return {
            "diff_status": "RESOLVED",
            "reason": "blank_nodes_present_graphs_isomorphic_no_structural_change",
            "rdf_triple_deletions": [],
            "rdf_triple_additions": [],
            "deletion_count": 0,
            "addition_count": 0,
            "unchanged": True,
        }

    # Isomorphism does not yield a unique trustworthy edit mapping.
    return {
        "diff_status": "AMBIGUOUS",
        "reason": (
            "blank_nodes_present_and_graphs_not_isomorphic;"
            " no unique triple edit mapping established"
        ),
        "before_triple_count": len(before),
        "after_triple_count": len(after),
        "rdf_triple_deletions": [],
        "rdf_triple_additions": [],
        "deletion_count": None,
        "addition_count": None,
        "unchanged": False,
    }


def _ground_diff(before: Graph, after: Graph) -> dict[str, Any]:
    before_map = {triple_key(t): t for t in before}
    after_map = {triple_key(t): t for t in after}
    deleted_keys = set(before_map) - set(after_map)
    added_keys = set(after_map) - set(before_map)
    deletions = [serialize_triple(before_map[k]) for k in sorted(deleted_keys)]
    additions = [serialize_triple(after_map[k]) for k in sorted(added_keys)]
    return {
        "diff_status": "RESOLVED",
        "reason": "no_blank_nodes_exact_triple_set_diff",
        "rdf_triple_deletions": deletions,
        "rdf_triple_additions": additions,
        "deletion_count": len(deletions),
        "addition_count": len(additions),
        "unchanged": len(deletions) == 0 and len(additions) == 0,
    }
