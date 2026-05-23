#!/usr/bin/env python3
"""Validate TEST-KIND metadata and generated test-index freshness."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[2]
ALLOWED_KINDS = {"unit", "integration", "stress"}
ALLOWED_STATUSES = {"LIVE", "PROBE", "STALE", "EXPLORATORY"}
MAX_PURPOSE_CHARS = 120


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    kind: str
    message: str

    def format(self, repo_root: Path) -> str:
        try:
            rel = self.path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = self.path.as_posix()
        return f"{rel}:{self.lineno}: {self.kind}: {self.message}"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARSER = _load_module(
    "codep_test_header_parser",
    PROJECT_ROOT / "scripts" / "test_header_parser.py",
)


def _first_line(parsed: dict, key: str) -> int:
    return parsed["line_numbers"].get(key, [parsed.get("first_test_lineno") or 1])[0]


def _missing(path: Path, parsed: dict, key: str) -> Violation:
    return Violation(path, parsed.get("first_executable_lineno") or 1, "metadata", f"missing {key}")


def validate_fixture(path: Path, repo_root: Path, behavior_baseline: set[str]) -> list[Violation]:
    parsed = PARSER.parse_test_kind_headers(path)
    headers = parsed["headers"]
    rel_path = PARSER.repo_relative(path, repo_root)
    violations: list[Violation] = []

    if path.suffix == ".tex" and parsed.get("late_test_lineno") is not None:
        violations.append(
            Violation(
                path,
                parsed["late_test_lineno"],
                "metadata",
                "TEST-* metadata must appear before executable TeX content",
            )
        )

    kind = headers.get("TEST-KIND", "").strip()
    if not kind:
        violations.append(_missing(path, parsed, "TEST-KIND"))
    elif kind not in ALLOWED_KINDS:
        violations.append(
            Violation(path, _first_line(parsed, "TEST-KIND"), "metadata", f"invalid TEST-KIND {kind!r}")
        )

    status = headers.get("TEST-STATUS", "").strip()
    if not status:
        violations.append(_missing(path, parsed, "TEST-STATUS"))
    elif status not in ALLOWED_STATUSES:
        violations.append(
            Violation(path, _first_line(parsed, "TEST-STATUS"), "metadata", f"invalid TEST-STATUS {status!r}")
        )

    purpose = headers.get("TEST-PURPOSE", "")
    if not purpose.strip():
        violations.append(_missing(path, parsed, "TEST-PURPOSE"))
    elif len(purpose) > MAX_PURPOSE_CHARS:
        violations.append(
            Violation(
                path,
                _first_line(parsed, "TEST-PURPOSE"),
                "metadata",
                f"TEST-PURPOSE exceeds {MAX_PURPOSE_CHARS} characters",
            )
        )

    render_modes = headers.get("TEST-RENDER-MODES", "").strip()
    if kind == "stress" and not render_modes:
        violations.append(_missing(path, parsed, "TEST-RENDER-MODES"))
    elif kind and kind != "stress" and render_modes:
        violations.append(
            Violation(
                path,
                _first_line(parsed, "TEST-RENDER-MODES"),
                "metadata",
                "TEST-RENDER-MODES is only allowed on TEST-KIND: stress fixtures",
            )
        )

    # Relationship to lint_traceability.py: that linter validates B-ID existence
    # for its .lvt scan scope. This linter only enforces that all indexed
    # fixtures either carry TEST-BEHAVIOR or are path-grandfathered.
    if (
        not headers.get("TEST-BEHAVIOR", "").strip()
        and not headers.get("TEST-EXEMPT", "").strip()
        and rel_path not in behavior_baseline
    ):
        violations.append(_missing(path, parsed, "TEST-BEHAVIOR"))

    return violations


def validate_tree(root: Path) -> list[Violation]:
    baseline = PARSER.read_behavior_baseline(PROJECT_ROOT)
    violations: list[Violation] = []
    for path in PARSER.iter_test_fixtures(root):
        if path.resolve() == SCRIPT_PATH:
            continue
        violations.extend(validate_fixture(path, PROJECT_ROOT, baseline))
    return violations


def _check_index_fresh() -> int:
    regenerator = _load_module(
        "codep_regenerate_test_index",
        PROJECT_ROOT / ".claude" / "scripts" / "regenerate_test_index.py",
    )
    return regenerator.regenerate(check=True)


def run_check(root: Path) -> int:
    violations = validate_tree(root)
    for violation in violations:
        print(violation.format(PROJECT_ROOT), file=sys.stderr)
    if violations:
        print(f"lint_test_kind: FAIL ({len(violations)} violation(s))", file=sys.stderr)
        return 1

    index_rc = _check_index_fresh()
    if index_rc != 0:
        print("lint_test_kind: FAIL (testfiles/test-index.md is stale)", file=sys.stderr)
        return 1

    print("lint_test_kind: PASS")
    return 0


def _synthetic_violation(content: str, suffix: str = ".lvt") -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as handle:
        handle.write(content)
        path = Path(handle.name)
    try:
        violations = validate_fixture(path, path.parent, set())
        return bool(violations)
    finally:
        path.unlink(missing_ok=True)


def run_self_test() -> int:
    valid_lvt = """%% TEST-NAME: synthetic
%% TEST-PURPOSE: Synthetic valid fixture.
%% TEST-KIND: unit
%% TEST-BEHAVIOR: B-NUM-SHARED
%% TEST-STATUS: LIVE
%% TEST-WHAT: Synthetic fixture.
\\documentclass{article}
"""
    valid_stress = """%% TEST-NAME: synthetic-stress
%% TEST-PURPOSE: Synthetic stress fixture.
%% TEST-KIND: stress
%% TEST-BEHAVIOR: B-REND-INLINE
%% TEST-STATUS: LIVE
%% TEST-RENDER-MODES: inline
\\documentclass{article}
"""
    cases = [
        ("missing TEST-KIND", valid_lvt.replace("%% TEST-KIND: unit\n", ""), ".lvt"),
        ("invalid TEST-KIND", valid_lvt.replace("%% TEST-KIND: unit", "%% TEST-KIND: visual"), ".lvt"),
        ("missing TEST-STATUS", valid_lvt.replace("%% TEST-STATUS: LIVE\n", ""), ".lvt"),
        ("missing TEST-PURPOSE", valid_lvt.replace("%% TEST-PURPOSE: Synthetic valid fixture.\n", ""), ".lvt"),
        ("missing stress render modes", valid_stress.replace("%% TEST-RENDER-MODES: inline\n", ""), ".tex"),
        (
            "header placement",
            "\\documentclass{article}\n%% TEST-KIND: unit\n%% TEST-PURPOSE: Too late.\n%% TEST-STATUS: LIVE\n%% TEST-BEHAVIOR: B-NUM-SHARED\n",
            ".tex",
        ),
    ]

    caught = 0
    missed: list[str] = []
    for name, content, suffix in cases:
        if _synthetic_violation(content, suffix):
            caught += 1
        else:
            missed.append(name)

    total = len(cases)
    if missed:
        print("self-test: FAIL")
        for name in missed:
            print(f"  missed synthetic violation: {name}")
        return 1

    print(f"self-test: PASS ({caught}/{total} synthetic violations caught)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate fixture TEST-KIND metadata (default)")
    parser.add_argument("--root", default=str(PROJECT_ROOT / "testfiles"), help="fixture root to scan")
    parser.add_argument("--self-test", action="store_true", help="run in-memory synthetic violation tests")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    return run_check(Path(args.root))


if __name__ == "__main__":
    sys.exit(main())
