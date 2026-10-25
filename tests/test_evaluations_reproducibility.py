
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "evaluations"

@pytest.mark.skipif(not PKG.is_dir(), reason="evaluations package missing")
def test_package_manifest_has_nine_cases():
    package = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    assert package["n_cases"] == 9
    assert len(package["cases"]) == 9
    assert (PKG / "README.md").is_file()
    assert (PKG / "checksums.sha256").is_file()
    assert (PKG / "run_evaluations.py").is_file()
    assert (PKG / "prepare_evaluations.py").is_file()

@pytest.mark.skipif(not PKG.is_dir(), reason="evaluations package missing")
def test_copy_cases_have_vendored_graphs_matching_checksums():
    import hashlib

    for case_dir in sorted((PKG / "cases").iterdir()):
        meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        if meta["redistribution"] != "copy":
            continue
        for role, info in meta["files"].items():
            path = case_dir / "graphs" / f"{role}.ttl"
            assert path.is_file(), path
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == info["sha256"], role

@pytest.mark.skipif(not PKG.is_dir(), reason="evaluations package missing")
def test_prepare_and_run_evaluations():
    import os

    mat = subprocess.run(
        [sys.executable, str(PKG / "prepare_evaluations.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert mat.returncode == 0, mat.stderr + mat.stdout

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    run = subprocess.run(
        [sys.executable, str(PKG / "run_evaluations.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    summary = json.loads(run.stdout)
    assert summary["all_ok"] is True
    assert summary["n_ok"] == 9
