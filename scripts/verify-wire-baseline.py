#!/usr/bin/env python3
"""
scripts/verify-wire-baseline.py

Re-compile the same fixtures as capture-wire-baseline.py, compare sha256
values against the committed manifest, and exit non-zero on any mismatch.

Run under nix develop:
  nix develop --command python3 scripts/verify-wire-baseline.py
      # default manifest is W05-XPARSE-VMODE-FIXES via capture-wire-baseline.py
  nix develop --command python3 scripts/verify-wire-baseline.py \\
      --manifest testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the capture pipeline without renaming the dash-containing file
# ---------------------------------------------------------------------------
_CAPTURE_PATH = Path(__file__).parent / "capture-wire-baseline.py"
_spec = importlib.util.spec_from_file_location("_cap", _CAPTURE_PATH)
_cap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cap)

PROJECT_ROOT = _cap.PROJECT_ROOT

# Default manifest path (backward-compat with unaudited callsites)
_DEFAULT_MANIFEST_PATH = _cap.MANIFEST_PATH


def _parse_args() -> "argparse.Namespace":
    parser = argparse.ArgumentParser(
        description="Verify wire-format baseline sha256 manifest."
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Path to the manifest JSON to verify against. "
            f"Default: {_DEFAULT_MANIFEST_PATH}"
        ),
    )
    return parser.parse_args()


def _compare(
    name: str,
    expected: "dict",
    current: "dict",
    mismatches: "list[str]",
) -> None:
    for field in ("aux_sha", "cdp_sha", "pdf_objects_sha"):
        exp = expected.get(field)
        cur = current.get(field)
        if exp is None and cur is None:
            continue
        if exp != cur:
            mismatches.append(
                f"  {name!r} {field}:\n"
                f"    expected {exp!r}\n"
                f"    current  {cur!r}"
            )


def main() -> None:
    args = _parse_args()

    if args.manifest is not None:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = PROJECT_ROOT / manifest_path
    else:
        manifest_path = _DEFAULT_MANIFEST_PATH

    if not manifest_path.exists():
        print(
            f"ERROR: manifest not found at {manifest_path}\n"
            "Run capture-wire-baseline.py first.",
            file=sys.stderr,
        )
        sys.exit(2)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_list: "list[dict]" = manifest.get("fixtures", [])

    fixture_map = _cap.find_fixture_files()
    mismatches: "list[str]" = []
    errors: "list[str]" = []

    for entry in expected_list:
        name: str = entry["name"]
        is_stress = name in _cap.STRESS_VARIANTS
        is_wc = name.endswith(" [warm-changed]")
        base_name = name[: -len(" [warm-changed]")] if is_wc else name

        print(
            f"  {'[stress] ' if is_stress else '[wc]    ' if is_wc else '         '}"
            f"{name}"
        )

        if is_stress:
            aux_sha, cdp_sha, pdf_sha = _cap.compile_stress(name)
            current = {
                "name": name,
                "aux_sha": aux_sha,
                "cdp_sha": cdp_sha,
                "pdf_objects_sha": pdf_sha,
            }
        else:
            fixture_path = fixture_map.get(base_name)
            if fixture_path is None:
                errors.append(f"  {base_name!r}: fixture file not found")
                continue

            if is_wc:
                aux_sha, cdp_sha = _cap.compile_warm_changed(
                    fixture_path, base_name
                )
            else:
                aux_sha, cdp_sha = _cap.compile_regular(
                    fixture_path, base_name
                )

            current = {
                "name": name,
                "aux_sha": aux_sha,
                "cdp_sha": cdp_sha,
                "pdf_objects_sha": None,
            }

        _compare(name, entry, current, mismatches)

    if errors:
        print("\nERRORS (fixtures not found):")
        for e in errors:
            print(e)

    if mismatches:
        print("\nMISMATCHES (wire-format changed since baseline):")
        for m in mismatches:
            print(m)
        sys.exit(1)

    if errors:
        sys.exit(2)

    print(f"\nAll {len(expected_list)} fixtures match the baseline.")


if __name__ == "__main__":
    main()
