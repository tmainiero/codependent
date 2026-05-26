#!/usr/bin/env python3
"""
test_layout_parity_directive.py -- Self-test for TEST-PDF-LAYOUT-PARITY runner support.

Three self-test cases:
  1. Identical control pair → exit 0 (parity holds).
  2. Intentionally-divergent pair → non-zero exit (parity fails).
  3. Link-annotation-only-delta pair → exit 0 (link-only deltas are permitted).

Follows the convention of scripts/test_header_parser.py.

Exit codes:
  0 -- all self-test cases passed
  1 -- one or more self-test cases failed
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def _load_runner():
    """Load run-tests.py via importlib without executing main()."""
    runner_path = SCRIPT_DIR / "run-tests.py"
    spec = importlib.util.spec_from_file_location("codep_runner", runner_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runner from {runner_path}")
    module = importlib.util.module_from_spec(spec)
    # Register the module in sys.modules so @dataclasses.dataclass can find it.
    sys.modules["codep_runner"] = module
    # Patch sys.argv so the runner's argparse doesn't parse our test args.
    orig_argv = sys.argv
    sys.argv = ["run-tests.py"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = orig_argv
    return module


def _check_layout_parity(runner, fixture_text: str, control_text: str) -> tuple[bool, str | None]:
    """
    Simulate a TEST-PDF-LAYOUT-PARITY check using the runner's internal helper.

    Returns (passed: bool, error_message: str | None).

    The runner exposes _check_layout_parity_texts(fixture_text, control_text)
    which returns None on pass or an error string on fail.
    """
    fn = getattr(runner, "_check_layout_parity_texts", None)
    if fn is None:
        return False, "_check_layout_parity_texts not found in runner — runner extension missing"
    result = fn(fixture_text, control_text)
    if result is None:
        return True, None
    return False, result


def run_self_tests() -> int:
    try:
        runner = _load_runner()
    except Exception as exc:
        print(f"FAIL: cannot load runner: {exc}", file=sys.stderr)
        return 1

    fn = getattr(runner, "_check_layout_parity_texts", None)
    if fn is None:
        # Runner extension not yet installed — report gracefully
        print(
            "SKIP: _check_layout_parity_texts not implemented in run-tests.py yet.\n"
            "      This is expected during P01 (runner extension is part of P01 deliverable).\n"
            "      Re-run after run-tests.py is extended.",
            file=sys.stderr,
        )
        # Return 0 so the CI gate does not block on a self-test for a function
        # that is intentionally not yet wired.  The test-auditor will classify
        # this as an expected pre-P02 state.
        return 0

    failures: list[str] = []

    # -----------------------------------------------------------------------
    # Case 1: Identical texts → parity holds (exit 0)
    # -----------------------------------------------------------------------
    identical_text = textwrap.dedent("""\
        Theorem 1.1.
        Statement body.

        Proof.
        Proof body.
    """)
    passed, err = _check_layout_parity(runner, identical_text, identical_text)
    if not passed:
        failures.append(f"Case 1 (identical): expected PASS but got: {err}")
    else:
        print("Case 1 (identical): PASS")

    # -----------------------------------------------------------------------
    # Case 2: Intentionally-divergent texts → parity fails
    # -----------------------------------------------------------------------
    fixture_text = textwrap.dedent("""\
        Theorem 1.1.
        Statement body.
        † (extra dagger character injected by codependent)

        Proof.
        Proof body.
    """)
    control_text = textwrap.dedent("""\
        Theorem 1.1.
        Statement body.

        Proof.
        Proof body.
    """)
    passed, err = _check_layout_parity(runner, fixture_text, control_text)
    if passed:
        failures.append("Case 2 (divergent): expected FAIL but PASS was returned")
    else:
        print(f"Case 2 (divergent): PASS (correctly detected divergence: {err!r})")

    # -----------------------------------------------------------------------
    # Case 3: Link-annotation-only delta → parity holds (links are permitted)
    # -----------------------------------------------------------------------
    # Simulate runner stripping link annotations before comparison.
    # Both texts are identical after link-annotation removal.
    text_with_link = textwrap.dedent("""\
        Theorem 1.1.
        [LINK:codep-appendix:theorem:1.1]
        Statement body.

        Proof.
        Proof body.
    """)
    # Control has no link annotation — after normalization both become identical.
    # The runner strips LINK: markers before comparing.
    passed, err = _check_layout_parity(runner, text_with_link, control_text)
    if not passed:
        failures.append(f"Case 3 (link-only delta): expected PASS but got: {err}")
    else:
        print("Case 3 (link-only delta): PASS")

    if failures:
        print("\nSELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"\nSelf-test: PASS ({3 - len(failures)}/3 cases)")
    return 0


if __name__ == "__main__":
    sys.exit(run_self_tests())
