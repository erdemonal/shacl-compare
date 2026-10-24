"""Minimal formal notes for the implemented comparison semantics.

This is the in-repo formal-model surface for SHACL Compare (not SHACL en Forme).
"""

from __future__ import annotations

ORIGINAL_CONSTRAINT_SEMANTICS = {
    "version": "0.1.3-custom-cc",
    "fixed_interface": {
        "baseline": "V(G0, S0)",
        "intervention_A": "V(GA, S0)",
        "intervention_B": "V(G0, SB)",
        "original_on_A": "filter designated constraint instance in V(GA, S0)",
        "original_on_B": "filter designated constraint instance in V(G0, S0)",
    },
    "designated_constraint_instance": (
        "Identified by focus_key, result_path (or path_fingerprint), "
        "source_shape, source_constraint_component, severity, and — for "
        "SPARQLConstraintComponent or user-defined ConstraintComponents — a "
        "structural sparql_fingerprint (SPARQL:… or CUSTOMCC:…) from the "
        "baseline ValidationResult / shapes graph. Original evaluation does "
        "not use graph-wide conforms."
    ),
    "outcomes": {
        "SATISFIED": (
            "Focus remains targeted under S0 and no ValidationResult matches the "
            "designated constraint-instance signature in V(data_branch, S0). "
            "For SPARQLConstraintComponent and custom ConstraintComponents this "
            "requires a structural fingerprint; absence alone is never SATISFIED."
        ),
        "VIOLATED": (
            "Focus remains targeted under S0 and at least one matching "
            "ValidationResult remains in V(data_branch, S0)."
        ),
        "NOT_EVALUATED": (
            "Target membership lost/unknown/ambiguous; blank-focus identity "
            "missing or non-unique; unstable path may hide a match; SPARQL/"
            "CUSTOMCC fingerprint unavailable or unannotated sibling results may "
            "hide a match; or cardinality cross-check disagreement. A uniquely "
            "resolved blank focus with no matching ValidationResult may be "
            "SATISFIED (aligned with CLEAR) when identity is otherwise reliable."
        ),
    },
    "distinct_from_clear_persist": (
        "CLEAR/PERSIST under a branch uses that branch's validation shapes "
        "(S0 for A, SB for B). Original-constraint always uses S0. Therefore B "
        "may be CLEAR under SB while original remains VIOLATED under S0."
    ),
    "shacl_sparql_note": (
        "Ordinary sh:sparql / SPARQLConstraintComponent executes under pySHACL "
        "with advanced=False. The advanced flag enables SHACL Advanced Features, "
        "not SHACL-SPARQL. Matching uses structural select/prefixes fingerprints, "
        "not blank sourceConstraint ids. User-defined SPARQL-based constraint "
        "components also run with advanced=False; CUSTOMCC fingerprints bind "
        "component IRI, parameter values on the source shape, and validator query."
    ),
    "limitations": [
        "Depends on pySHACL emitting sourceConstraintComponent (and preferably "
        "sourceConstraint) for the designated failure.",
        "Does not separately evaluate nested sub-shape semantics inside logical constraints.",
        "pySHACL 0.40.x executes ordinary sh:sparql with sh:select only; sh:ask "
        "on sh:sparql nodes is unsupported. SPARQLAskValidator for custom "
        "constraint components is supported (via sh:validator in pySHACL 0.40.x).",
        "pySHACL maps sh:propertyValidator/sh:nodeValidator to SELECT validators "
        "and sh:validator to ASK validators; W3C examples that put SELECT on "
        "sh:validator may need propertyValidator/nodeValidator under pySHACL.",
        "Custom CC fingerprints require IRI parameter paths and literal/IRI "
        "parameter values; blank parameter paths/values yield NOT_COMPARABLE/"
        "DesignateError rather than invented identity.",
        "Identical SPARQL or CUSTOMCC fingerprints on the same shape remain "
        "ambiguous without --designation-index / unique shape identity.",
        "Complex/blank resultPath satisfaction claims require stable path fingerprints.",
        "Cardinality arithmetic remains a transitional cross-check for ordinary minCount/maxCount "
        "on verified IRI PredicatePaths only.",
        "QualifiedMinCount / QualifiedMaxCount original-constraint uses the S0 ValidationResult "
        "filter only; values are never counted as ordinary minCount/maxCount.",
        "resultSeverity is part of designated constraint-instance identity; a severity "
        "change in SB can CLEAR the designated failure while emitting a new residual "
        "at another severity.",
        "sh:deactivated clearing a ValidationResult under SB is not original satisfaction; "
        "original-constraint still filters V(data, S0).",
        "pySHACL may report graph non-conformance for Warning/Info results; Compare "
        "outcomes use ValidationResult matching, not graph-wide conforms.",
        "SHACL Advanced Features (rules, functions, node expressions, etc.) are out of scope.",
    ],
}
