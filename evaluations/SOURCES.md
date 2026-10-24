# Evaluation sources and redistribution

SHACL Compare evaluation package under `evaluations/`.

## Redistribution policy

### 1. Copied into `cases/*/graphs/` (`redistribution=copy`)

- W3C data-shapes test-suite lineage cases and evaluator-authored synthetic other-focus case.
- W3C materials are under the [W3C Software and Document License](http://www.w3.org/Consortium/Legal/copyright-software).
- GA/SB (and G0/S0 splits) were constructed by the evaluator for comparison experiments; they are **not** patches published by upstream maintainers.

### 2. Prepared at runtime (`redistribution=materialize`); not vendored as large trees

#### `04_dcat_ap_lu_title` and `09_dcat_ap_lu_title_resource`

- Upstream: https://github.com/meaningfy-ws/dcat-ap-lu
- Pin: `e62932a78be506673de9234fa25be3089e20264d`
- License evidence: README.md §License states documents/reports/specifications are CC-BY-4.0. No root LICENSE / SPDX file was found in the pinned tree.
- Conservative handling: fetch pinned shapes/data at prepare time (user-side retrieval with checksum verification); do not vendor the large shapes file.
- Small evaluator G0/GA fixtures for case 04 are under `inputs/` (evaluator-normalized / intervention artefacts). Case 04 G0/GA are RDF-isomorphic to the pinned DCAT-AP-LU invalid-title fixture plus title repair. Case 09 uses the verbatim upstream invalid-title fixture and a URI-valued `dct:title` repair.
- Historical identifiers: `04_c_eval_v01_dcat_ap_lu_title`, `09_V6_dcat_ap_lu_title_NEW`.

#### `05_dcat_ap_rights`

- DCAT-AP: https://github.com/SEMICeu/DCAT-AP @ `4470b8ea907b7eb9ec55ab22befd1ecd2210ff32`
  - License: CC-BY-4.0 (GitHub license metadata + LICENSE file).
- GeoDCAT-AP: https://github.com/SEMICeu/GeoDCAT-AP @ `7e7d6a82f4bd4491c68f774f185193439881ab42`
  - License: CC-BY-4.0 (GitHub license metadata + LICENSE file).
- G0 is extracted from the pinned GeoDCAT-AP HTML free-text multi-rights example; S0/SB from pinned DCAT-AP SHACL with a deterministic `sh:maxCount` deletion on the Distribution `dct:rights` property shape; GA under `inputs/` detaches the INSPIRE `dct:rights` statement from the Distribution.
- Historical identifier: `05_c_eval_v02_dcat_ap_rights`.

### 3. Attribution

When redistributing SEMIC CC-BY-4.0 materials, retain upstream copyright notices and license. Evaluator interventions are not upstream patches.

`prepare_evaluations.py` performs pinned HTTPS retrieval + checksum verification and writes graphs to `.workdir/` (gitignored). SHA-256 values in `case.json` / `checksums.sha256` validate the reconstructed evaluation inputs.

Do not claim evaluator-created repairs/revisions were made by upstream projects.
