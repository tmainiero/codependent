#!/usr/bin/env python3
"""lint_no_sbl.py -- Drift linter: reject legacy sbl symbols in active code.

Scans ACTIVE_PATHS and ACTIVE_GLOBS for tokens that indicate residual
.sbl-era naming in active source files.  Historical prose (docs/DESIGN.md,
docs/HISTORY.md, .claude/comms/, memory/) is intentionally excluded from
the scan scope.

Run: python3 .claude/scripts/lint_no_sbl.py
Self-test: python3 .claude/scripts/lint_no_sbl.py --self-test
"""
import pathlib
import re
import sys
import tempfile

# ---------------------------------------------------------------------------
# Configuration -- top-of-file, no JSON/yaml indirection
# ---------------------------------------------------------------------------

ACTIVE_PATHS = [
    "codependent.sty",
    "codependent-render.sty",
    "scripts/run-tests.py",
]

ACTIVE_GLOBS = [
    ".claude/scripts/*.py",
    "scripts/*.sh",
]

# Linter's own implementation/test strings are excluded by self-path check
# below (see _is_self).
REJECTED_TOKENS = [
    r"\\codep@sbl@",
    r"codependent/sbl/",
    r"\bfix\.sbl_",
    r"\bsbl_contains\b",
    r"\bsbl_not_contains\b",
    r"\bsbl_count\b",
    r"\bsbl_last_record\b",
]

_COMPILED = [re.compile(t) for t in REJECTED_TOKENS]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_self(path: pathlib.Path) -> bool:
    return path.resolve() == pathlib.Path(__file__).resolve()


def _scan(path: pathlib.Path) -> list:
    """Return list of (lineno, token_pattern, line) for each hit."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pat, compiled in zip(REJECTED_TOKENS, _COMPILED):
            if compiled.search(line):
                hits.append((lineno, pat, line.rstrip()))
                break  # one hit per line is enough
    return hits


def _resolve_paths(repo_root, extra_globs=None):
    """Resolve ACTIVE_PATHS + ACTIVE_GLOBS (+ optional extras) to a deduped list."""
    seen = set()
    result = []

    globs = ACTIVE_GLOBS + (extra_globs or [])

    for rel in ACTIVE_PATHS:
        p = (repo_root / rel).resolve()
        if p not in seen:
            seen.add(p)
            result.append(p)

    for glob_pat in globs:
        for p in sorted(repo_root.glob(glob_pat)):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                result.append(rp)

    return result


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------


def run_scan(repo_root, extra_globs=None):
    """Scan all active files; return exit code (0=PASS, 1=FAIL)."""
    paths = _resolve_paths(repo_root, extra_globs)

    total_files = 0
    total_hits = 0
    hit_files = set()

    for path in paths:
        if _is_self(path):
            continue
        if not path.exists():
            try:
                rel = path.relative_to(repo_root)
            except ValueError:
                rel = path
            print(f"lint_no_sbl: WARN: {rel} missing")
            continue
        total_files += 1
        hits = _scan(path)
        for lineno, pat, line in hits:
            try:
                rel = path.relative_to(repo_root)
            except ValueError:
                rel = path
            print(f"{rel}:{lineno}: {pat}: {line}")
            total_hits += 1
            hit_files.add(path)

    if total_hits == 0:
        print(f"lint_no_sbl: PASS ({total_files} files scanned, 0 hits)")
        return 0
    else:
        print(f"lint_no_sbl: FAIL ({total_hits} hits in {len(hit_files)} files)")
        return 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_self_test():
    """Verify the linter catches synthetic violations; return 0 on success."""
    synthetic_cases = [
        (r"\\codep@sbl@",         r"\codep@sbl@foo{bar}"),
        (r"codependent/sbl/",     r"\DeclareHookRule{...}{codependent/sbl/open}"),
        (r"\bfix\.sbl_",          r"for x in fix.sbl_contains:"),
        (r"\bsbl_contains\b",     r"    sbl_contains: list = dataclasses.field(...)"),
        (r"\bsbl_not_contains\b", r"    sbl_not_contains: list = dataclasses.field(...)"),
        (r"\bsbl_count\b",        r"    sbl_count: list = dataclasses.field(...)"),
        (r"\bsbl_last_record\b",  r'    sbl_last_record: str = ""'),
    ]

    caught = 0
    missed = []

    for pattern_str, line in synthetic_cases:
        compiled = re.compile(pattern_str)
        if compiled.search(line):
            caught += 1
        else:
            missed.append(f"  MISSED pattern={pattern_str!r} line={line!r}")

    n = len(synthetic_cases)

    # Also verify via a real tempfile injected into the file scan.
    content_lines = [line for _, line in synthetic_cases]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                     delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(content_lines) + "\n")
        tmp_path = pathlib.Path(tf.name)

    try:
        hits = _scan(tmp_path)
        file_caught = len(hits)
        if file_caught != n:
            missed.append(
                f"  File scan caught {file_caught}/{n} violations (expected {n})"
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    if missed:
        print("self-test: FAIL")
        for m in missed:
            print(m)
        return 1

    print(f"self-test: PASS (caught {caught}/{n} synthetic violations)")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    sys.exit(run_scan(repo_root))
