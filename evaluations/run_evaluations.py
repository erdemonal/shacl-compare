#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parent
WORKDIR = PKG / ".workdir"
_REPO = PKG.parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from shacl_compare.compare import CompareConfig, run_compare  # noqa: E402


def _graphs_dir(meta: dict, case_dir: Path) -> Path:
    if meta["redistribution"] == "copy":
        return case_dir / "graphs"
    return WORKDIR / meta["id"] / "graphs"


def run_case(case_dir: Path) -> dict:
    meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    gdir = _graphs_dir(meta, case_dir)
    required = [gdir / f"{r}.ttl" for r in ("G0", "S0", "GA", "SB")]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        return {
            "id": meta["id"],
            "ok": False,
            "error": "missing_graphs",
            "missing": missing,
            "hint": "run prepare_evaluations.py for redistribution=materialize cases",
        }

    d = meta["designated"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.json"
        report = run_compare(
            CompareConfig(
                data_baseline=gdir / "G0.ttl",
                shapes_baseline=gdir / "S0.ttl",
                data_repair=gdir / "GA.ttl",
                shapes_revision=gdir / "SB.ttl",
                focus=d["focus"],
                path=d["path"],
                source_shape=d.get("source_shape"),
                component=d["component"],
                severity=d.get("severity")
                or "http://www.w3.org/ns/shacl#Violation",
                focus_key_properties=[],
                requirement_card=None,
                out=out,
                designation_index=d.get("designation_index"),
            )
        )

    obs = {
        "A_outcome": report["intervention_A"]["result_outcome"],
        "B_outcome": report["intervention_B"]["result_outcome"],
        "A_original": report["intervention_A"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ],
        "B_original": report["intervention_B"]["original_constraint_evaluation"][
            "original_constraint_evaluation"
        ],
    }
    exp = meta["current_expected"]
    diffs = {k: {"expected": exp[k], "observed": obs[k]} for k in exp if exp[k] != obs[k]}
    return {
        "id": meta["id"],
        "inventory_name": meta["inventory_name"],
        "ok": not diffs,
        "observed": obs,
        "expected": exp,
        "diffs": diffs,
        "historical_vs_current_deltas": meta.get("historical_vs_current_deltas", []),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Run evaluation cases and check case.json expectations."
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for machine-readable summary JSON",
    )
    args = p.parse_args(argv)

    results = []
    for case_dir in sorted((PKG / "cases").iterdir()):
        if (case_dir / "case.json").is_file():
            results.append(run_case(case_dir))

    n_ok = sum(1 for r in results if r.get("ok"))
    summary = {
        "package": "evaluations",
        "n": len(results),
        "n_ok": n_ok,
        "all_ok": n_ok == len(results) == 12,
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
