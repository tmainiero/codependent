#!/usr/bin/env python3
"""Hard-fail if W05-INSTALL-DISCIPLINE-CORE tries to rotate wire baselines."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_BASELINE_REL = Path("testfiles/baselines/W05-INSTALL-DISCIPLINE-CORE")
FIXTURE_ROOT = (
    PROJECT_ROOT
    / ".claude"
    / "scripts"
    / "lint-fixtures"
    / "wire-format-no-rotation"
)


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def check_root(root: Path) -> list[str]:
    baseline_dir = root / CORE_BASELINE_REL
    if baseline_dir.exists():
        return [
            f"ERROR: {_rel(root, baseline_dir)}: unexpected CORE baseline directory; "
            "verify against testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json instead"
        ]
    return []


def run_self_test() -> int:
    if not FIXTURE_ROOT.exists():
        print(f"ERROR: missing fixture root {FIXTURE_ROOT}")
        return 1
    with tempfile.TemporaryDirectory(prefix="codep-no-rotation-fixture-") as tmp:
        root = Path(tmp)
        shutil.copytree(FIXTURE_ROOT, root, dirs_exist_ok=True)
        planted = root / CORE_BASELINE_REL
        planted.mkdir(parents=True, exist_ok=True)
        diagnostics = check_root(root)
        expected = (
            "ERROR: testfiles/baselines/W05-INSTALL-DISCIPLINE-CORE: "
            "unexpected CORE baseline directory; verify against "
            "testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json instead"
        )
        if diagnostics != [expected]:
            print("ERROR: wire-format no-rotation fixture mismatch")
            print("expected:")
            print(expected)
            print("actual:")
            print("\n".join(diagnostics) if diagnostics else "PASS")
            return 1
    print("PASS: wire-format no-rotation empty-dir fixture detected the forbidden directory")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(PROJECT_ROOT),
        help="Project root to inspect (default: repository root).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the planted empty-dir fixture self-test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    root = Path(args.root).resolve()
    diagnostics = check_root(root)
    for diagnostic in diagnostics:
        print(diagnostic)
    if diagnostics:
        return 1
    print("PASS: no W05-INSTALL-DISCIPLINE-CORE wire baseline directory exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
