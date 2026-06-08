#!/usr/bin/env python3
"""lint_fixture_warnings.py — validate TEST-REQUIRES/TOLERATES-WARNING annotations.

Scans:
  testfiles/unit/*.lvt          (excludes selftest-*.lvt — meta-fixtures for runner)
  testfiles/integration/*.lvt
  testfiles/compiled-examples/*.tex

Each directive must have an adjacent non-empty %% reason: line immediately after.
Pattern validation: broadness rejection, extracted-class prefix, concrete discriminant,
valid Python regex.

Ratchet: .claude/baseline-warning-annotations.json (shrink-only).
  --update-ratchet  Write new baseline when current counts <= baseline; refused on growth.
"""

import argparse
import json
import re
import sys
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = REPO_ROOT / ".claude" / "baseline-warning-annotations.json"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Broadness rejection
# ---------------------------------------------------------------------------

_BROAD_EXACT = frozenset({
    "*", ".*", ".*?", ".+", "^.*$",
    "LaTeX Warning:.*", "LaTeX Warning:.+",
    "LaTeX Font Warning:.*", "LaTeX Font Warning:.+",
    "LaTeX|Package", "Warning", "Package Warning",
})

_BROAD_PKG_CLASS_RE = re.compile(r'^(?:Package|Class)\s+\S+\s+Warning:(?:\.\*|\.\+)\s*$')
_UNDERFULL_RE = re.compile(r'^Underfull\s')

# ---------------------------------------------------------------------------
# Extracted-class prefix check
# ---------------------------------------------------------------------------
# "Reference" and "There were" are recognized LaTeX Warning content fragments
# that appear at the start of specific well-known warning texts and are
# used in production fixtures.

_PREFIX_RE = re.compile(
    r'^(?:'
    r'LaTeX Warning:|'
    r'LaTeX Font Warning:|'
    r'Package \S+ Warning:|'
    r'Class \S+ Warning:|'
    r'Overfull\s|'
    r'Label|'
    r'Reference|'
    r'There were'
    r')'
)

_PREFIX_STRIP_RE = re.compile(
    r'^(?:'
    r'LaTeX Warning:\s*|'
    r'LaTeX Font Warning:\s*|'
    r'Package \S+ Warning:\s*|'
    r'Class \S+ Warning:\s*|'
    r'Overfull\s\S*\s*|'
    r'Label\S*\s*|'
    r'Reference\s*|'
    r'There were\s*'
    r')'
)


def _strip_prefix(pattern):
    m = _PREFIX_STRIP_RE.match(pattern)
    return pattern[m.end():] if m else pattern


def _has_discriminant(pattern):
    suffix = _strip_prefix(pattern)
    return bool(
        re.search(r'[a-zA-Z]{3,}', suffix)
        or re.search(r'\\[a-zA-Z]+', suffix)
        or re.search(r'\d{2,}', suffix)
    )


# ---------------------------------------------------------------------------
# Per-pattern validation
# ---------------------------------------------------------------------------

def validate_pattern(pattern, kind, path, lineno):
    errs = []

    if pattern in _BROAD_EXACT:
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING broadness-rejected exact pattern: {pattern!r}"
        )
        return errs

    if _BROAD_PKG_CLASS_RE.match(pattern):
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING broadness-rejected pkg/class wildcard: {pattern!r}"
        )
        return errs

    if _UNDERFULL_RE.match(pattern):
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING rejected: Underfull \\hbox is not an extracted class: {pattern!r}"
        )
        return errs

    try:
        re.compile(pattern)
    except re.error as exc:
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING invalid regex: {pattern!r} — {exc}"
        )
        return errs

    if not _PREFIX_RE.match(pattern):
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING missing extracted-class prefix: {pattern!r}"
        )
        return errs

    if not _has_discriminant(pattern):
        errs.append(
            f"{path}:{lineno}: TEST-{kind}-WARNING lacks concrete discriminant after prefix: {pattern!r}"
        )

    return errs


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

_DIRECTIVE_RE = re.compile(r'^%%\s+TEST-(REQUIRES|TOLERATES)-WARNING:\s*(.+?)\s*$')
_REASON_RE = re.compile(r'^%%\s+reason:\s*(\S.*)$')


def parse_file(filepath):
    try:
        text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        return [], [f"{filepath}: cannot read file — {exc}"]

    lines = text.splitlines()
    directives = []
    errors = []

    i = 0
    while i < len(lines):
        m = _DIRECTIVE_RE.match(lines[i])
        if m:
            kind = m.group(1)
            pattern = m.group(2)
            lineno = i + 1

            if i + 1 < len(lines) and _REASON_RE.match(lines[i + 1]):
                i += 2
            else:
                next_preview = repr(lines[i + 1]) if i + 1 < len(lines) else "<EOF>"
                errors.append(
                    f"{filepath}:{lineno}: TEST-{kind}-WARNING: missing adjacent "
                    f"non-empty %% reason: line (next line: {next_preview})"
                )
                i += 1

            errors.extend(validate_pattern(pattern, kind, filepath, lineno))
            directives.append((kind, pattern, lineno))
        else:
            i += 1

    return directives, errors


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def get_scan_files():
    unit = sorted([
        f for f in glob(str(REPO_ROOT / "testfiles" / "unit" / "*.lvt"))
        if not Path(f).name.startswith("selftest-")
    ])
    integration = sorted(glob(str(REPO_ROOT / "testfiles" / "integration" / "*.lvt")))
    compiled = sorted(glob(str(REPO_ROOT / "testfiles" / "compiled-examples" / "*.tex")))
    return unit + integration + compiled


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------

def load_baseline():
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text())
    return None


def write_baseline(total_requires, total_tolerates, per_fixture):
    data = {
        "schema_version": SCHEMA_VERSION,
        "requires_warning_count": total_requires,
        "tolerates_warning_count": total_tolerates,
        "per_fixture": {
            str(Path(k).resolve().relative_to(REPO_ROOT)): v
            for k, v in sorted(per_fixture.items())
        },
    }
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate TEST-REQUIRES/TOLERATES-WARNING annotations."
    )
    parser.add_argument(
        "--update-ratchet",
        action="store_true",
        help="Write new baseline when current counts <= baseline. Refused on growth.",
    )
    parser.add_argument(
        "files", nargs="*",
        help="Files to scan (default: all fixture directories).",
    )
    args = parser.parse_args()

    files = args.files if args.files else get_scan_files()

    all_errors = []
    per_fixture = {}
    total_requires = 0
    total_tolerates = 0

    for filepath in files:
        directives, errors = parse_file(filepath)
        all_errors.extend(errors)

        req = sum(1 for k, _, _ in directives if k == "REQUIRES")
        tol = sum(1 for k, _, _ in directives if k == "TOLERATES")

        if req + tol > 0:
            per_fixture[filepath] = {"requires": req, "tolerates": tol}

        total_requires += req
        total_tolerates += tol

    for err in all_errors:
        print(f"ERROR: {err}", file=sys.stderr)

    baseline = load_baseline()

    if args.update_ratchet:
        if all_errors:
            print(
                "ERROR: --update-ratchet refused: fix validation errors first",
                file=sys.stderr,
            )
            sys.exit(1)

        if baseline is not None:
            grew = []
            if total_requires > baseline["requires_warning_count"]:
                grew.append(
                    f"requires_warning_count: {baseline['requires_warning_count']} → {total_requires}"
                )
            if total_tolerates > baseline["tolerates_warning_count"]:
                grew.append(
                    f"tolerates_warning_count: {baseline['tolerates_warning_count']} → {total_tolerates}"
                )
            if grew:
                for msg in grew:
                    print(f"ERROR: --update-ratchet refused: growth detected: {msg}", file=sys.stderr)
                sys.exit(1)

        write_baseline(total_requires, total_tolerates, per_fixture)
        print(
            f"Baseline written: requires={total_requires} tolerates={total_tolerates} "
            f"fixtures={len(per_fixture)}"
        )
        sys.exit(0)

    if all_errors:
        print(f"FAILED: {len(all_errors)} validation error(s)", file=sys.stderr)
        sys.exit(1)

    if baseline is None:
        print(
            "WARN: no baseline found; run --update-ratchet to create initial baseline",
            file=sys.stderr,
        )
        print(
            f"Current: requires={total_requires} tolerates={total_tolerates} "
            f"fixtures={len(per_fixture)}"
        )
        sys.exit(0)

    req_base = baseline["requires_warning_count"]
    tol_base = baseline["tolerates_warning_count"]
    failed = False

    if total_requires > req_base:
        print(
            f"ERROR: requires_warning_count grew: {req_base} → {total_requires} "
            f"(+{total_requires - req_base})",
            file=sys.stderr,
        )
        failed = True
    elif total_requires < req_base:
        print(
            f"INFO: requires_warning_count shrunk {req_base} → {total_requires}; "
            f"run --update-ratchet to confirm shrinkage"
        )

    if total_tolerates > tol_base:
        print(
            f"ERROR: tolerates_warning_count grew: {tol_base} → {total_tolerates} "
            f"(+{total_tolerates - tol_base})",
            file=sys.stderr,
        )
        failed = True
    elif total_tolerates < tol_base:
        print(
            f"INFO: tolerates_warning_count shrunk {tol_base} → {total_tolerates}; "
            f"run --update-ratchet to confirm shrinkage"
        )

    if failed:
        sys.exit(1)

    print(
        f"PASS: requires={total_requires} tolerates={total_tolerates} "
        f"fixtures={len(per_fixture)}"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
