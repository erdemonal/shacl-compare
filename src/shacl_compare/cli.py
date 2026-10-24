from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdflib.namespace import SH

from shacl_compare.compare import CompareConfig, run_compare
from shacl_compare.designate import DesignateError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shacl-compare",
        description=(
            "Compare a supplied RDF data repair and SHACL constraint revision "
            "against the same designated validation failure."
        ),
    )
    p.add_argument("--data-baseline", type=Path, required=True)
    p.add_argument("--shapes-baseline", type=Path, required=True)
    p.add_argument("--data-repair", type=Path, required=True)
    p.add_argument("--shapes-revision", type=Path, required=True)
    p.add_argument("--focus", required=True, help="Focus node IRI or blank-node focus key")
    p.add_argument(
        "--path",
        required=True,
        help=(
            "Designated sh:resultPath. Use an absolute IRI for a PredicatePath, "
            "or empty/non-IRI text for node-level or complex paths matched by "
            "structural fingerprint."
        ),
    )
    p.add_argument(
        "--source-shape",
        default=None,
        help=(
            "Optional absolute IRI of sh:sourceShape. Omit for anonymous property "
            "shapes (matched by focus, path, component, and severity). Useful for "
            "complex paths so fingerprints resolve across graph reloads."
        ),
    )
    p.add_argument("--component", required=True)
    p.add_argument(
        "--severity",
        default=str(SH.Violation),
        help=f"Default: {SH.Violation}",
    )
    p.add_argument(
        "--designation-index",
        type=int,
        default=None,
        help=(
            "1-based index when focus, path, component, and severity match more than "
            "one baseline ValidationResult."
        ),
    )
    p.add_argument(
        "--focus-key",
        dest="focus_key_properties",
        action="append",
        default=[],
        help="Property IRI used to build blank-node focus keys (repeatable)",
    )
    p.add_argument("--requirement-card", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = CompareConfig(
        data_baseline=args.data_baseline,
        shapes_baseline=args.shapes_baseline,
        data_repair=args.data_repair,
        shapes_revision=args.shapes_revision,
        focus=args.focus,
        path=args.path,
        source_shape=args.source_shape,
        component=args.component,
        severity=args.severity,
        focus_key_properties=args.focus_key_properties,
        requirement_card=args.requirement_card,
        out=args.out,
        designation_index=args.designation_index,
    )
    try:
        report = run_compare(cfg)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except DesignateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    cfg.out.write_text(
        json.dumps(report, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
