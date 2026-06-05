#!/usr/bin/env python3
"""check-exclusion-ranges.py — W05-HYGIENE-ETOOLBOX-IDIOMS exclusion-range gate.

Reads the wave-base SHA from .claude/comms/W05-HYGIENE-etoolbox-wave-base.sha,
diffs the two .sty files against that base commit, and checks every hunk against
the E01-E12 protected range table.

Exit code: 0 = PASS, 1 = violation found.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SHA_FILE = Path(".claude/comms/W05-HYGIENE-etoolbox-wave-base.sha")

PROTECTED_RANGES = [
    {
        "id": "E01",
        "file": "codependent-render.sty",
        "start": 191,
        "end": 201,
        "mode": "wrapper-only",
        "wrapper_lines": {198},
        "description": "Render cache freeze. Wrapper may change at :198; body :199-201 byte-identical.",
    },
    {
        "id": "E02",
        "file": "codependent.sty",
        "start": 4742,
        "end": 4746,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Aux renderlist wire write body. Protected write payload must not change.",
    },
    {
        "id": "E03",
        "file": "codependent.sty",
        "start": 6455,
        "end": 6456,
        "mode": "wrapper-only",
        "wrapper_lines": {6455},
        "description": "Token-safe print-kind capture. Wrapper may change at :6455; body :6456 byte-identical.",
    },
    {
        "id": "E04",
        "file": "codependent.sty",
        "start": 6626,
        "end": 6627,
        "mode": "wrapper-only",
        "wrapper_lines": {6626},
        "description": "Token-safe entity print-kind capture. Wrapper may change at :6626; body :6627 byte-identical.",
    },
    {
        "id": "E05",
        "file": "codependent-render.sty",
        "start": 84,
        "end": 90,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Collapse accumulator \\unexpanded choreography; no \\csname wrapper to modernize.",
    },
    {
        "id": "E06",
        "file": "codependent-render.sty",
        "start": 348,
        "end": 350,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Appendix emit triple-dispatch supplies a control-sequence token; do not replace with \\csuse.",
    },
    {
        "id": "E07",
        "file": "codependent.sty",
        "start": 2996,
        "end": 2999,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Deferred proofof payload; \\unexpanded{#1} must stay literal through deferred execution.",
    },
    {
        "id": "E08",
        "file": "codependent.sty",
        "start": 4687,
        "end": 4695,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Entitymeta accumulator copies existing accumulator and display field under \\unexpanded.",
    },
    {
        "id": "E09",
        "file": "codependent.sty",
        "start": 4764,
        "end": 4766,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Renderlist triple-dispatch supplies a control-sequence token.",
    },
    {
        "id": "E10",
        "file": "codependent.sty",
        "start": 4797,
        "end": 4804,
        "mode": "wrapper-only",
        "wrapper_lines": {4797},
        "description": "Pending ref write payload. Wrapper may change at :4797; body :4798-4804 byte-identical.",
    },
    {
        "id": "E11",
        "file": "codependent.sty",
        "start": 6429,
        "end": 6431,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "Appendix-display pgfkeys value capture.",
    },
    {
        "id": "E12",
        "file": "codependent.sty",
        "start": 6588,
        "end": 6588,
        "mode": "off-limits",
        "wrapper_lines": set(),
        "description": "tcolorbox print-kind final capture; token-safe xdef stays raw.",
    },
]

# Hunk header: @@ -OLD[,N] +NEW[,M] @@
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
# File header line
_FILE_RE = re.compile(r"^(?:---|\+\+\+) [ab]/(.+)$")


def _read_sha() -> str:
    if not SHA_FILE.exists():
        sys.exit(f"error: wave-base SHA file missing: {SHA_FILE}")
    sha = SHA_FILE.read_text().strip()
    if not sha:
        sys.exit(f"error: wave-base SHA file is empty: {SHA_FILE}")
    return sha


def _verify_commit(sha: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(
            f"error: wave-base commit {sha!r} not found in repo (git cat-file -e failed)"
        )


def _run_diff(sha: str) -> str:
    result = subprocess.run(
        [
            "git",
            "diff",
            "-U0",
            sha,
            "--",
            "codependent.sty",
            "codependent-render.sty",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        sys.exit(
            f"error: git diff failed (exit {result.returncode}):\n{result.stderr}"
        )
    return result.stdout


def _parse_hunks(diff_text: str) -> list[tuple[str, int, int]]:
    """Return list of (filename, old_start, old_count) for each hunk."""
    hunks: list[tuple[str, int, int]] = []
    current_file: str | None = None

    for line in diff_text.splitlines():
        file_match = _FILE_RE.match(line)
        if file_match:
            if line.startswith("+++"):
                current_file = file_match.group(1)
            continue

        hunk_match = _HUNK_RE.match(line)
        if hunk_match and current_file is not None:
            old_start = int(hunk_match.group(1))
            # When the ,N part is omitted, git means N=1.
            old_count = (
                int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
            )
            hunks.append((current_file, old_start, old_count))

    return hunks


def _check_hunk(
    filename: str, old_start: int, old_count: int, entry: dict
) -> str | None:
    """Return a violation message, or None if this hunk is clean for this entry."""
    if filename != entry["file"]:
        return None

    estart: int = entry["start"]
    eend: int = entry["end"]
    mode: str = entry["mode"]
    wrapper_lines: set[int] = entry["wrapper_lines"]
    eid: str = entry["id"]

    is_pure_insertion = old_count == 0

    if is_pure_insertion:
        # Caveat 1 (R5-MAJOR-01): a pure insertion whose OLD coordinate falls inside
        # the protected range is a gap-overlap and fails regardless of wrapper_lines.
        if estart <= old_start <= eend:
            return (
                f"{filename}:{old_start} {eid} [{mode}]: "
                f"pure insertion (N==0) at old-side line {old_start} "
                f"inside protected range {estart}-{eend} "
                f"(gap-overlap, fails regardless of wrapper_lines)"
            )
        return None

    # Regular hunk: old-side range is [old_start, old_start + old_count - 1].
    hunk_end = old_start + old_count - 1

    if hunk_end < estart or old_start > eend:
        return None  # no overlap at all

    if mode == "off-limits":
        return (
            f"{filename}:{old_start}-{hunk_end} {eid} [off-limits]: "
            f"hunk overlaps protected range {estart}-{eend}"
        )

    # wrapper-only: allowed only if every overlapping old-side line is in wrapper_lines.
    overlap_start = max(old_start, estart)
    overlap_end = min(hunk_end, eend)
    forbidden = [
        ln
        for ln in range(overlap_start, overlap_end + 1)
        if ln not in wrapper_lines
    ]
    if forbidden:
        lines_str = ", ".join(str(ln) for ln in forbidden[:5])
        if len(forbidden) > 5:
            lines_str += f", ... ({len(forbidden)} total)"
        return (
            f"{filename}:{old_start}-{hunk_end} {eid} [wrapper-only]: "
            f"hunk touches non-wrapper lines {lines_str} inside protected range {estart}-{eend}"
        )
    return None


def main() -> None:
    sha = _read_sha()
    _verify_commit(sha)
    diff_text = _run_diff(sha)
    hunks = _parse_hunks(diff_text)

    violations: list[str] = []
    for filename, old_start, old_count in hunks:
        for entry in PROTECTED_RANGES:
            msg = _check_hunk(filename, old_start, old_count, entry)
            if msg is not None:
                violations.append(msg)

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}", file=sys.stderr)
        sys.exit(1)

    print(
        f"exclusion-check: PASS "
        f"({len(hunks)} hunks scanned, {len(PROTECTED_RANGES)} E-entries enforced)"
    )


if __name__ == "__main__":
    main()
