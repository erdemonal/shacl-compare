#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PKG = Path(__file__).resolve().parent
WORKDIR = PKG / ".workdir"
CACHE = WORKDIR / "_cache"
INPUTS = PKG / "inputs"


UPSTREAM = {
    "dcat_ap_lu_data": {
        "url": (
            "https://raw.githubusercontent.com/meaningfy-ws/dcat-ap-lu/"
            "e62932a78be506673de9234fa25be3089e20264d/"
            "tests/test_data/shacl/dcat-Dataset-dct-title/"
            "dcat-Dataset-dct-title_invalid.ttl"
        ),
        "sha256": "73eb114c0079d7d7fbf9459dcab2f9e358c5d7f160e41ac001bf888ebb691d15",
        "filename": "dcat_ap_lu_data.ttl",
    },
    "dcat_ap_lu_shapes": {
        "url": (
            "https://raw.githubusercontent.com/meaningfy-ws/dcat-ap-lu/"
            "e62932a78be506673de9234fa25be3089e20264d/"
            "implementation/dcat_ap_lu/shacl_shapes/dcat_ap_lu_CM_shapes.ttl"
        ),
        "sha256": "1e817609fb9f38a5c67740bf2813a3693bb6cbbd7ea3259658fc0e294ac2130e",
        "filename": "dcat_ap_lu_shapes.ttl",
    },
    "dcat_ap_shapes": {
        "url": (
            "https://raw.githubusercontent.com/SEMICeu/DCAT-AP/"
            "4470b8ea907b7eb9ec55ab22befd1ecd2210ff32/"
            "releases/3.0.0/shacl/dcat-ap-SHACL.ttl"
        ),
        "sha256": "92f76609d78d257123e75bc6b7155df5cc0a63f14c29fbc12b0ac95c56af2059",
        "filename": "dcat_ap_SHACL_3.0.0.ttl",
    },
    "geodcat_html": {
        "url": (
            "https://raw.githubusercontent.com/SEMICeu/GeoDCAT-AP/"
            "7e7d6a82f4bd4491c68f774f185193439881ab42/"
            "releases/3.0.0/index.html"
        ),
        "sha256": "c6916b14824967956009b9ec8961b105be802c794620e3b41ce46ebcb97225ae",
        "filename": "geodcat_ap_3.0.0_index.html",
    },
}

_LU_TITLE_MINCOUNT_OLD = (
    "core-res:dcat-Dataset-dct-title a sh:PropertyShape ;\n"
    "    rdfs:isDefinedBy core-res:core-shape ;\n"
    "    sh:datatype rdfs:Literal ;\n"
    '    sh:description "A name given to the Dataset" ;\n'
    "    sh:minCount 1 ;\n"
    '    sh:name "title" ;\n'
    "    sh:path dcterms:title ."
)
_LU_TITLE_MINCOUNT_NEW = _LU_TITLE_MINCOUNT_OLD.replace(
    "sh:minCount 1 ;", "sh:minCount 0 ;"
)

_09_GA_OLD = (
    "ex:dataset-no-title a dcat:Dataset ;\n"
    '    dct:identifier "dataset-001" ;\n'
    '    dct:description "No title provided." .'
)
_09_GA_NEW = (
    "ex:dataset-no-title a dcat:Dataset ;\n"
    '    dct:identifier "dataset-001" ;\n'
    '    dct:description "No title provided." ;\n'
    "    dct:title ex:SomeTitleResource ."
)

_DCAT_RIGHTS_MAXCOUNT_OLD = (
    "<https://semiceu.github.io/DCAT-AP/releases/3.0.0/shacl/dcat-ap-SHACL.ttl"
    "#dcat:DistributionShape/3844f5a8620973800a0f9d6121572dbe0082c955> "
    'rdfs:seeAlso "https://semiceu.github.io/DCAT-AP/releases/3.0.0#Distribution.rights";\n'
    '  shacl:description "A statement that specifies rights associated with the Distribution."@en;\n'
    "  shacl:maxCount 1;\n"
    '  shacl:name "rights"@en;\n'
    "  shacl:path dc:rights ."
)
_DCAT_RIGHTS_MAXCOUNT_NEW = (
    "<https://semiceu.github.io/DCAT-AP/releases/3.0.0/shacl/dcat-ap-SHACL.ttl"
    "#dcat:DistributionShape/3844f5a8620973800a0f9d6121572dbe0082c955> "
    'rdfs:seeAlso "https://semiceu.github.io/DCAT-AP/releases/3.0.0#Distribution.rights";\n'
    '  shacl:description "A statement that specifies rights associated with the Distribution."@en;\n'
    '  shacl:name "rights"@en;\n'
    "  shacl:path dc:rights ."
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _replace_exactly_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly 1 occurrence of edit anchor, found {n}")
    return text.replace(old, new, 1)


def fetch_upstream(key: str) -> bytes:
    meta = UPSTREAM[key]
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / meta["filename"]
    if dest.is_file() and sha256_path(dest) == meta["sha256"]:
        return dest.read_bytes()
    try:
        with urllib.request.urlopen(meta["url"], timeout=60) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"failed to fetch {key} from {meta['url']}: {exc}. "
            "Network access is required for clean-checkout preparation."
        ) from exc
    digest = sha256_bytes(data)
    if digest != meta["sha256"]:
        raise RuntimeError(
            f"upstream sha256 mismatch for {key}: got {digest}, expected {meta['sha256']}"
        )
    dest.write_bytes(data)
    return data


def extract_geodcat_g0(html_bytes: bytes) -> bytes:
    """Deterministic extraction of the GeoDCAT free-text RDF example."""
    html = html_bytes.decode("utf-8")
    aside_m = re.search(
        r'id="ex-mapping-conditions-for-access-and-use".*?</aside>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not aside_m:
        raise RuntimeError("GeoDCAT HTML: aside#ex-mapping-conditions-for-access-and-use not found")
    aside = aside_m.group(0)
    pre_m = re.search(
        r"free-text version:.*?<pre[^>]*>(.*?)</pre>",
        aside,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not pre_m:
        raise RuntimeError("GeoDCAT HTML: free-text Turtle <pre> not found")
    raw = re.sub(r"<[^>]+>", "", html_lib.unescape(pre_m.group(1)))
    body = raw.strip() + "\n"
    return (
        "@prefix dcat: <http://www.w3.org/ns/dcat#> .\n"
        "@prefix dct:  <http://purl.org/dc/terms/> .\n\n"
        + body
    ).encode("utf-8")


def _write_role(dest_dir: Path, role: str, data: bytes, expected: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{role}.ttl"
    if dest.exists():
        dest.chmod(0o644)
        dest.unlink()
    dest.write_bytes(data)
    dest.chmod(0o644)
    digest = sha256_bytes(data)
    if digest != expected:
        raise RuntimeError(
            f"{dest_dir.parent.name}: {role} sha256 mismatch "
            f"(got {digest}, expected {expected})"
        )


def build_04(roles: dict) -> dict[str, bytes]:
    shapes = fetch_upstream("dcat_ap_lu_shapes")
    sb = _replace_exactly_once(
        shapes.decode("utf-8"),
        _LU_TITLE_MINCOUNT_OLD,
        _LU_TITLE_MINCOUNT_NEW,
        "04 SB minCount",
    ).encode("utf-8")
    return {
        "G0": (INPUTS / "04_G0.ttl").read_bytes(),
        "S0": shapes,
        "GA": (INPUTS / "04_GA.ttl").read_bytes(),
        "SB": sb,
    }


def build_05(roles: dict) -> dict[str, bytes]:
    html = fetch_upstream("geodcat_html")
    shapes = fetch_upstream("dcat_ap_shapes")
    sb = _replace_exactly_once(
        shapes.decode("utf-8"),
        _DCAT_RIGHTS_MAXCOUNT_OLD,
        _DCAT_RIGHTS_MAXCOUNT_NEW,
        "05 SB maxCount",
    ).encode("utf-8")
    return {
        "G0": extract_geodcat_g0(html),
        "S0": shapes,
        "GA": (INPUTS / "05_GA.ttl").read_bytes(),
        "SB": sb,
    }


def build_09(roles: dict) -> dict[str, bytes]:
    data = fetch_upstream("dcat_ap_lu_data")
    shapes = fetch_upstream("dcat_ap_lu_shapes")
    ga = _replace_exactly_once(
        data.decode("utf-8"),
        _09_GA_OLD,
        _09_GA_NEW,
        "09 GA title insert",
    ).encode("utf-8")
    sb = _replace_exactly_once(
        shapes.decode("utf-8"),
        _LU_TITLE_MINCOUNT_OLD,
        _LU_TITLE_MINCOUNT_NEW,
        "09 SB minCount",
    ).encode("utf-8")
    return {
        "G0": data,
        "S0": shapes,
        "GA": ga,
        "SB": sb,
    }


BUILDERS = {
    "04_dcat_ap_lu_title": build_04,
    "05_dcat_ap_rights": build_05,
    "09_dcat_ap_lu_title_resource": build_09,
}


def prepare(verify_only: bool = False) -> int:
    errors: list[str] = []
    ok = 0
    for case_dir in sorted((PKG / "cases").iterdir()):
        meta_path = case_dir / "case.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mode = meta["redistribution"]
        roles = meta["files"]
        if mode == "copy":
            gdir = case_dir / "graphs"
            for role, info in roles.items():
                target = gdir / f"{role}.ttl"
                if not target.is_file():
                    errors.append(f"{meta['id']}: missing vendored {target}")
                    continue
                digest = sha256_path(target)
                if digest != info["sha256"]:
                    errors.append(
                        f"{meta['id']}: {role} sha256 mismatch "
                        f"(got {digest}, expected {info['sha256']})"
                    )
                else:
                    ok += 1
            continue

        dest_dir = WORKDIR / meta["id"] / "graphs"
        builder = BUILDERS.get(meta["id"])
        if builder is None:
            errors.append(f"{meta['id']}: no clean-checkout builder registered")
            continue

        if verify_only:
            for role, info in roles.items():
                path = dest_dir / f"{role}.ttl"
                if not path.is_file():
                    errors.append(f"{meta['id']}: missing {role} at {path}")
                    continue
                digest = sha256_path(path)
                if digest != info["sha256"]:
                    errors.append(
                        f"{meta['id']}: {role} sha256 mismatch "
                        f"(got {digest}, expected {info['sha256']})"
                    )
                else:
                    ok += 1
            continue

        try:
            built = builder(roles)
            for role, info in roles.items():
                if role not in built:
                    errors.append(f"{meta['id']}: builder omitted {role}")
                    continue
                _write_role(dest_dir, role, built[role], info["sha256"])
                ok += 1
        except Exception as exc:  # noqa: BLE001 — surface as prepare error
            errors.append(f"{meta['id']}: {exc}")

    print(f"verified_files={ok}")
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("prepare_ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Fetch and construct graphs for prepare-mode evaluation cases."
    )
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="Check checksums of already-prepared graphs without rebuilding",
    )
    args = p.parse_args(argv)
    return prepare(verify_only=args.verify_only)


if __name__ == "__main__":
    raise SystemExit(main())
