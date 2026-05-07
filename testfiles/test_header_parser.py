"""Shared TEST-* header parsing for codependent fixtures.

The parser is intentionally tiny and importable via
``importlib.util.spec_from_file_location`` so project scripts under
``.claude/scripts`` and ``testfiles/run-tests.py`` can share one definition
without turning either directory into a Python package.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SKIP_DIR_NAMES = {"output", "tmp", "corpus", "__pycache__"}
HEADER_RE = re.compile(
    r"^%{1,2}\s+(TEST-[A-Z0-9-]+)(?:\[(cold|warm|warm_changed)\])?:\s*(.*)$"
)


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("%")


def _is_late_header(line: str) -> bool:
    return HEADER_RE.match(line) is not None


def parse_test_kind_headers(path: Path) -> dict:
    """Parse top-of-file TEST-* headers from ``path``.

    Both ``%% TEST-*`` and ``% TEST-*`` syntax are accepted. Headers are
    collected only before the first executable (non-comment, non-blank) line.
    TEST-* lines later in the file are reported through ``late_test_lineno`` so
    lint can reject compiled ``.tex`` fixtures whose metadata appears below
    ``\\documentclass`` or another TeX primitive.
    """

    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    values: dict[str, list[str]] = defaultdict(list)
    line_numbers: dict[str, list[int]] = defaultdict(list)
    entries: list[dict] = []
    first_executable_lineno: int | None = None
    first_test_lineno: int | None = None
    late_test_lineno: int | None = None

    for lineno, line in enumerate(lines, start=1):
        if first_executable_lineno is None and _is_comment_or_blank(line):
            match = HEADER_RE.match(line)
            if match:
                key = match.group(1)
                phase = match.group(2)
                value = match.group(3).strip()
                stored_key = f"{key}[{phase}]" if phase else key
                values[stored_key].append(value)
                line_numbers[stored_key].append(lineno)
                entries.append(
                    {
                        "key": key,
                        "phase": phase,
                        "stored_key": stored_key,
                        "value": value,
                        "lineno": lineno,
                        "raw": line,
                    }
                )
                if first_test_lineno is None:
                    first_test_lineno = lineno
            continue

        if first_executable_lineno is None:
            first_executable_lineno = lineno

        if late_test_lineno is None and _is_late_header(line):
            late_test_lineno = lineno

    first_values = {key: vals[0] for key, vals in values.items() if vals}
    return {
        "path": path,
        "entries": entries,
        "values": dict(values),
        "headers": first_values,
        "line_numbers": dict(line_numbers),
        "first_executable_lineno": first_executable_lineno,
        "first_test_lineno": first_test_lineno,
        "late_test_lineno": late_test_lineno,
        "line_count": len(lines),
    }


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a POSIX-style path relative to ``repo_root`` when possible."""

    path = Path(path)
    repo_root = Path(repo_root)
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_fixture_path(path: Path) -> bool:
    """True for source fixture files the metadata index owns."""

    path = Path(path)
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if path.suffix == ".lvt":
        return True
    return path.suffix == ".tex" and "compiled-examples" in path.parts


def iter_test_fixtures(root: Path) -> Iterable[Path]:
    """Yield .lvt fixtures and compiled-example .tex fixtures under ``root``."""

    root = Path(root)
    seen: set[Path] = set()

    for path in sorted(root.rglob("*.lvt")):
        if is_fixture_path(path):
            resolved = path.resolve()
            seen.add(resolved)
            yield path

    compiled_dir = root / "compiled-examples"
    tex_paths = compiled_dir.glob("*.tex") if compiled_dir.exists() else root.rglob("*.tex")
    for path in sorted(tex_paths):
        if is_fixture_path(path):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def read_behavior_baseline(repo_root: Path) -> set[str]:
    """Read path entries from .test-behavior-baseline.

    The same file also contains grandfathered B-* IDs for visible-verification
    ratchets. This helper intentionally returns only fixture paths.
    """

    baseline = Path(repo_root) / ".test-behavior-baseline"
    if not baseline.exists():
        return set()
    paths: set[str] = set()
    for raw_line in baseline.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("testfiles/"):
            paths.add(Path(line).as_posix())
    return paths
