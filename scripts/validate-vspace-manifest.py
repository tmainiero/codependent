#!/usr/bin/env python3
"""
validate-vspace-manifest.py -- Validate the VSPACE transition manifest.

Checks:
  1. Loads testfiles/vspace-inventory-manifest.json.
  2. Ensures every entry has "status" in {"asserted", "waived"}.
  3. For "asserted" entries: parses the fixture at assertion_line; confirms
     it is a TEST-PDF-VSPACE-BETWEEN directive; confirms anchor regexes
     plausibly match from_env and to_env via prefix-match on env name.
  4. For "waived" entries: confirms "reason" is non-empty.
  5. Stale-entry detection: cross-checks manifest entries against the
     generated inventory at --inventory; flags entries whose
     (fixture, from_env, to_env, line_span) no longer appear in inventory.

Usage:
  python3 scripts/validate-vspace-manifest.py \\
      --inventory testfiles/output/vspace-inventory.json

Exit codes:
  0 -- all checks pass
  1 -- validation errors found
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
MANIFEST_PATH = REPO_ROOT / "testfiles" / "vspace-inventory-manifest.json"

VSPACE_DIRECTIVE_RE = re.compile(
    r"^%%\s+TEST-PDF-VSPACE-BETWEEN:\s+(.+)$"
)


def load_json(path: Path, label: str) -> object:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"validate-vspace-manifest: ERROR: {label} not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"validate-vspace-manifest: ERROR: {label} is invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def env_in_regex(env_name: str, regex_str: str) -> bool:
    """Heuristic prefix-match: does the regex plausibly reference the env name?"""
    # Accept if env name appears literally or as escaped tokens in the regex,
    # or if the regex is a common proof/theorem pattern.
    lower_env = env_name.lower()
    lower_regex = regex_str.lower()
    # Simple heuristic: env name substring after unescaping \\s, \\. etc.
    unescaped = re.sub(r'\\[sSdDwW\.\*\+\?\^\$\{\}\[\]\(\)\|]', ' ', lower_regex)
    unescaped = re.sub(r'\\\\', '', unescaped)
    # Check if first word of regex contains the env name as substring
    words = re.findall(r'\w+', unescaped)
    env_words = re.findall(r'\w+', lower_env)
    for ew in env_words:
        for rw in words:
            if ew in rw or rw in ew:
                return True
    return False


def validate(manifest_path: Path, inventory_path: Path) -> list[str]:
    errors: list[str] = []

    manifest_data = load_json(manifest_path, "manifest")
    if not isinstance(manifest_data, dict):
        errors.append("manifest: root must be a JSON object")
        return errors

    entries = manifest_data.get("entries", [])
    if not isinstance(entries, list):
        errors.append("manifest: 'entries' must be a JSON array")
        return errors

    inventory_data = load_json(inventory_path, "inventory")
    if not isinstance(inventory_data, list):
        errors.append("inventory: root must be a JSON array")
        return errors

    # Build lookup set from inventory: (fixture, from_env, to_env, tuple(line_span))
    inventory_set: set[tuple] = set()
    for item in inventory_data:
        if isinstance(item, dict):
            key = (
                item.get("fixture", ""),
                item.get("from_env", ""),
                item.get("to_env", ""),
                tuple(item.get("line_span", [])),
            )
            inventory_set.add(key)

    for idx, entry in enumerate(entries):
        prefix = f"entries[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: must be a JSON object")
            continue

        status = entry.get("status", "")
        if status not in ("asserted", "waived"):
            errors.append(
                f"{prefix}: 'status' must be 'asserted' or 'waived', got {status!r}"
            )
            continue

        fixture = entry.get("fixture", "")
        from_env = entry.get("from_env", "")
        to_env = entry.get("to_env", "")
        line_span = entry.get("line_span", [])

        for req in ("fixture", "from_env", "to_env", "line_span"):
            if req not in entry:
                errors.append(f"{prefix}: missing required field {req!r}")

        if status == "asserted":
            assertion_line = entry.get("assertion_line")
            max_points = entry.get("max_points")
            if assertion_line is None:
                errors.append(f"{prefix}: 'asserted' entry missing 'assertion_line'")
            if max_points is None:
                errors.append(f"{prefix}: 'asserted' entry missing 'max_points'")

            # Check fixture file exists and assertion_line is TEST-PDF-VSPACE-BETWEEN
            if fixture and assertion_line is not None:
                fixture_path = REPO_ROOT / fixture
                if not fixture_path.exists():
                    errors.append(
                        f"{prefix}: fixture not found: {fixture_path}"
                    )
                else:
                    try:
                        with open(fixture_path, encoding="utf-8") as f:
                            lines = f.readlines()
                        lineno = int(assertion_line)
                        if lineno < 1 or lineno > len(lines):
                            errors.append(
                                f"{prefix}: assertion_line {lineno} out of range "
                                f"(file has {len(lines)} lines)"
                            )
                        else:
                            line = lines[lineno - 1].rstrip()
                            m = VSPACE_DIRECTIVE_RE.match(line)
                            if not m:
                                errors.append(
                                    f"{prefix}: line {lineno} in {fixture} is not "
                                    f"a TEST-PDF-VSPACE-BETWEEN directive: {line!r}"
                                )
                            else:
                                # Parse the spec to extract anchor regexes
                                import shlex
                                try:
                                    parts = shlex.split(m.group(1))
                                    if len(parts) >= 2:
                                        anchor1, anchor2 = parts[0], parts[1]
                                        if not env_in_regex(from_env, anchor1):
                                            errors.append(
                                                f"{prefix}: anchor1 regex {anchor1!r} does not "
                                                f"plausibly match from_env={from_env!r}"
                                            )
                                        if not env_in_regex(to_env, anchor2):
                                            errors.append(
                                                f"{prefix}: anchor2 regex {anchor2!r} does not "
                                                f"plausibly match to_env={to_env!r}"
                                            )
                                    else:
                                        errors.append(
                                            f"{prefix}: TEST-PDF-VSPACE-BETWEEN directive has "
                                            f"fewer than 2 quoted parts: {m.group(1)!r}"
                                        )
                                except ValueError as exc:
                                    errors.append(
                                        f"{prefix}: cannot parse VSPACE-BETWEEN spec: {exc}"
                                    )
                    except OSError as exc:
                        errors.append(f"{prefix}: cannot read fixture: {exc}")

            # Stale-entry check
            if fixture and from_env and to_env and line_span:
                inv_key = (fixture, from_env, to_env, tuple(line_span))
                if inv_key not in inventory_set:
                    errors.append(
                        f"{prefix}: stale entry — (fixture={fixture!r}, "
                        f"from_env={from_env!r}, to_env={to_env!r}, "
                        f"line_span={line_span!r}) not found in generated inventory"
                    )

        elif status == "waived":
            reason = entry.get("reason", "")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{prefix}: 'waived' entry must have non-empty 'reason'")

            # Stale-entry check for waived entries too
            if fixture and from_env and to_env and line_span:
                inv_key = (fixture, from_env, to_env, tuple(line_span))
                if inv_key not in inventory_set:
                    errors.append(
                        f"{prefix}: stale entry — (fixture={fixture!r}, "
                        f"from_env={from_env!r}, to_env={to_env!r}, "
                        f"line_span={line_span!r}) not found in generated inventory"
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="validate-vspace-manifest.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inventory",
        required=True,
        help="Path to the generated inventory JSON (testfiles/output/vspace-inventory.json)",
    )
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST_PATH),
        help="Path to the committed manifest JSON (default: testfiles/vspace-inventory-manifest.json)",
    )
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    manifest_path = Path(args.manifest)

    errors = validate(manifest_path, inventory_path)
    if errors:
        print("validate-vspace-manifest: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    entry_count = 0
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry_count = len(data.get("entries", []))
    except Exception:
        pass
    print(f"validate-vspace-manifest: PASS ({entry_count} entries validated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
