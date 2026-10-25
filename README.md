# SHACL Compare

SHACL Compare is a Python command-line tool for comparing a proposed RDF data repair with a proposed SHACL constraint revision for the validation failure. It uses [pySHACL](https://github.com/RDFLib/pySHACL) for validation and reports the effects of both changes without choosing a preferred intervention.

## Formal model

Let \(G_0\) be the original RDF data graph and \(S_0\) the original SHACL shapes graph. Let \(G_A\) be the data graph after a repair and \(S_B\) the shapes graph after a revision. For a SHACL validation procedure \(V\), the three validation runs are

$$
V_0 = V(G_0,S_0), \qquad
V_A = V(G_A,S_0), \qquad
V_B = V(G_0,S_B).
$$

A validation result \(\delta \in \mathrm{Results}(V_0)\) is designated for comparison. Its disappearance under \(V_A\) or \(V_B\) is reported separately from satisfaction of the original constraint under \(S_0\).

In particular, clearing \(\delta\) after changing \(S_0\) does not imply that the original constraint is satisfied:

$$
\mathrm{Clear}(\delta, V_B)
\not\Rightarrow
\mathrm{Satisfied}_{S_0}(\delta, G_0).
$$

The report compares the outcomes of both interventions, their effects on the original constraint, and any additional violations.

## Installation

Requires Python 3.10 or newer.

```bash
python -m pip install -e .
```

## Usage

Supply four Turtle files and identify a validation result from the baseline graph.

```bash
shacl-compare \
  --data-baseline evaluations/cases/01_max_count/graphs/G0.ttl \
  --shapes-baseline evaluations/cases/01_max_count/graphs/S0.ttl \
  --data-repair evaluations/cases/01_max_count/graphs/GA.ttl \
  --shapes-revision evaluations/cases/01_max_count/graphs/SB.ttl \
  --focus 'http://datashapes.org/sh/tests/core/property/maxCount-001.test#InvalidPerson' \
  --path 'http://datashapes.org/sh/tests/core/property/maxCount-001.test#firstName' \
  --source-shape 'http://datashapes.org/sh/tests/core/property/maxCount-001.test#PersonShape-firstName' \
  --component 'http://www.w3.org/ns/shacl#MaxCountConstraintComponent' \
  --out report.json
```

The JSON output separates the results of interventions A and B in `comparison` and records supporting validation and graph-change details. Run `shacl-compare --help` for additional arguments.

## Tests and evaluations

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python evaluations/prepare_evaluations.py
python evaluations/run_evaluations.py
```

The nine evaluation cases are stored in [`evaluations/cases/`](evaluations/cases/). Some require network access to retrieve pinned upstream materials. Provenance, attribution, and reconstruction details are documented in [`evaluations/README.md`](evaluations/README.md).

SHACL Compare analyzes data repairs and constraint revisions provided by the user. It uses pySHACL for validation and does not generate or rank solutions.