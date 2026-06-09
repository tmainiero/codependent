#!/usr/bin/env python3
"""Self-tests for the runner warning hygiene gate.

These cases exercise the pure Python gate logic directly with synthetic logs;
they do not invoke a TeX engine.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def _runner_candidates() -> list[Path]:
    return [
        SCRIPT_DIR / "run-tests.py",
        Path.cwd() / "scripts" / "run-tests.py",
        REPO_ROOT / "scripts" / "run-tests.py",
    ]


def _load_runner():
    """Load run-tests.py via importlib without executing main()."""
    runner_path = next((path for path in _runner_candidates() if path.is_file()), None)
    if runner_path is None:
        searched = ", ".join(str(path) for path in _runner_candidates())
        raise ImportError(f"cannot find run-tests.py; searched: {searched}")

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


def _gate_failures(runner, *, log_text: str, requires_warning: list[str] | None = None) -> list[str]:
    fixture = runner.Fixture(path=Path("synthetic-warning-gate.lvt"), name="synthetic-warning-gate")
    fixture.requires_warning = list(requires_warning or [])
    result = runner.TestResult(fixture=fixture, passed=True)

    with tempfile.TemporaryDirectory(prefix="codep-warning-gate-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / f"{fixture.name}.log").write_text(log_text, encoding="utf-8")
        runner._run_warning_gate(fixture, result, tmp_path)

    return result.failures


def test_undeclared_warning_fails_gate(runner) -> None:
    failures = _gate_failures(
        runner,
        log_text="\n".join(
            [
                "LaTeX Warning: Reference `missing-label' on page 1 undefined on input line 7.",
                "",
            ]
        ),
    )
    if not any("undeclared warning block" in failure for failure in failures):
        raise AssertionError(f"expected undeclared-warning failure, got {failures!r}")


def test_stale_required_warning_fails_gate(runner) -> None:
    failures = _gate_failures(
        runner,
        log_text="This synthetic final log has no warning blocks.\n",
        requires_warning=["xyzzy_never_emitted_selftest_marker_12345"],
    )
    if not any("did not match any warning block" in failure for failure in failures):
        raise AssertionError(f"expected stale-required-warning failure, got {failures!r}")


def run_self_tests() -> int:
    try:
        runner = _load_runner()
    except Exception as exc:  # noqa: BLE001 - print a terse self-test failure.
        print(f"FAIL: cannot load runner: {exc}", file=sys.stderr)
        return 1

    tests = [
        test_undeclared_warning_fails_gate,
        test_stale_required_warning_fails_gate,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test(runner)
        except Exception as exc:  # noqa: BLE001 - collect self-test failures.
            failures.append(f"{test.__name__}: {exc}")
        else:
            print(f"{test.__name__}: PASS")

    if failures:
        print("\nSELF-TEST FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"\nSelf-test: PASS ({len(tests)}/{len(tests)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(run_self_tests())
