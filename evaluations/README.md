# Evaluation Sources

The twelve evaluation cases use W3C SHACL tests, DCAT application profiles, and additional RDF graphs prepared for this study. Source files and modifications are documented below.

## W3C SHACL Tests

Cases 01 and 02 adapt tests from the W3C SHACL test suite. Case 03 uses a synthetic example. The graphs for these cases are stored in `evaluations/cases/`.

The W3C materials are covered by the [W3C Software and Document License](https://www.w3.org/copyright/software-license/).

The RDF data repairs and SHACL constraint revisions were prepared for this study. They are not modifications published by the original authors.

## DCAT Application Profiles

### Cases 04 and 09

Source: [DCAT AP LU](https://github.com/meaningfy-ws/dcat-ap-lu)

Commit: `e62932a78be506673de9234fa25be3089e20264d`

The original SHACL shapes and RDF examples come from this repository. Case 04 uses locally prepared RDF graphs, and Case 09 uses the original invalid title example with a modified title value.

The upstream documentation states that its specifications and reports are distributed under CC BY 4.0.

### Case 05

Sources:

- [DCAT AP](https://github.com/SEMICeu/DCAT-AP), commit `4470b8ea907b7eb9ec55ab22befd1ecd2210ff32`
- [GeoDCAT AP](https://github.com/SEMICeu/GeoDCAT-AP), commit `7e7d6a82f4bd4491c68f774f185193439881ab42`

The RDF graph comes from a GeoDCAT AP example containing multiple rights statements. The SHACL shapes come from DCAT AP 3.0.0.

The data repair removes one rights statement from the Distribution. The constraint revision removes the corresponding `sh:maxCount` restriction.

Both upstream repositories distribute their materials under CC BY 4.0.

## Boundary Outcomes (Cases 10–12)

Cases 10–12 are synthetic fixtures adapted from the unit-test suite. They extend the evaluation beyond designated `CLEAR`/`CLEAR` pairs.

### Case 10 — SPARQL literal whitespace

The baseline SPARQL constraint requires a label literal with two internal spaces. The data edit adds a one-space label and does not remove the designated failure (`PERSIST`). The shapes revision changes the query literal to one space (`CLEAR` of the designated fingerprint). Under the revised shapes with unchanged baseline data, a new SPARQL violation appears for the revised query.

### Case 11 — Sequence path revision

The shapes revision replaces the sequence path `(ex:address ex:code)` with `(ex:address ex:postalCode)`. Shape alignment is unresolved, so the designated outcome under revision is `NOT_COMPARABLE`. The data-side input for this case is the unchanged baseline graph (`GA` identical to `G0`). It is not a data repair; side A is a no-op re-validation that leaves the designated failure (`PERSIST`).

### Case 12 — Target loss

The data edit removes `rdf:type ex:Person` while retaining two `ex:firstName` values. The designated MaxCount result disappears (`CLEAR`) because the node leaves `targetClass` membership (`LOST`). Original-constraint evaluation under `S0` is `NOT_EVALUATED` (`focus_not_targeted`). The shapes revision raises `sh:maxCount` from 1 to 2 and clears the designated failure while retaining target membership.

## Reproducing the Evaluations

The original sources for cases 04, 05, and 09 are retrieved from the specified commits. `prepare_evaluations.py` reconstructs the graphs and verifies their SHA256 checksums.

The remaining evaluation graphs are stored directly in the repository. Their checksums are recorded in `evaluations/checksums.sha256`.

```bash
python evaluations/prepare_evaluations.py
PYTHONPATH=src python evaluations/run_evaluations.py
```

The prepared graphs for materialize-mode cases are written to `evaluations/.workdir/`.

## Graph IRI Normalization

Cases 01 and 02 contain normalized IRIs for W3C test metadata. Local file identifiers were replaced with portable IRIs under `http://datashapes.org/sh/tests/`. The SHACL constraints and designated focus nodes were not changed.

The identifier mappings are recorded in the corresponding `case.json` files.
