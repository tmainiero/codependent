#!/usr/bin/env python3
"""
semtex.sty test runner.

Runs every .lvt fixture under unit/ and integration/ through pdflatex
(plus the optional real-world/wrappers/), parses the TEST-* metadata
header in each fixture, applies assertions, and produces a summary.

Designed to run BEFORE semtex.sty's implementation phase: assertions
target observable artifacts (.aux, .sbl, .log, exit code) rather than
golden .tlg files. l3build can later replace this runner once the
implementation lands and we can lock in golden output.

Usage:

    python3 run-tests.py [--filter PATTERN] [--engine pdflatex|lualatex|xelatex]
                         [--keep-temp] [--verbose] [--unit-only]
                         [--integration-only] [--real-world]

System-wide texlive-full is used during the design/test phase per
user direction 2026-04-09 (the project's Nix flake does not yet
include all required packages). The runner detects the system tex
binary at startup and prints a notice. Future runs (post-implementation)
should go through `nix develop` with a flake that has the full deps.

Standard library only. No PyYAML, no requests, no third-party deps.
"""

import argparse
import dataclasses
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import defaultdict
from pathlib import Path

# ----------------------------------------------------------------------
# Project layout
# ----------------------------------------------------------------------

# Path of THIS script: tools/semtex-sty/testfiles/run-tests.py
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # tools/semtex-sty/
UNIT_DIR = SCRIPT_DIR / "unit"
INTEGRATION_DIR = SCRIPT_DIR / "integration"
REAL_WORLD_DIR = SCRIPT_DIR / "real-world" / "wrappers"

# Where the .sty file lives. The runner copies it into the temp work dir
# so each test sees a clean kpse search path.
STY_FILE = PROJECT_ROOT / "semtex.sty"
LTXML_FILE = PROJECT_ROOT / "semtex.ltxml"  # may not exist yet


# ----------------------------------------------------------------------
# Test metadata model
# ----------------------------------------------------------------------

METADATA_KEYS = {
    "TEST-NAME": "name",
    "TEST-WHAT": "what",
    "TEST-SOURCE": "source",
    "TEST-SECTION": "section",
    "TEST-EXIT": "exit_code",
    "TEST-LOG-NOT": "log_not",  # may repeat
    "TEST-LOG-CONTAINS": "log_contains",  # may repeat
    "TEST-SBL-CONTAINS": "sbl_contains",  # may repeat
    "TEST-SBL-NOT-CONTAINS": "sbl_not_contains",  # may repeat
    "TEST-SBL-COUNT": "sbl_count",  # "<pattern> = <n>", may repeat
    "TEST-AUX-CONTAINS": "aux_contains",  # may repeat
    "TEST-AUX-NOT-CONTAINS": "aux_not_contains",  # may repeat
    "TEST-ATOMS-MIN": "atoms_min",
    "TEST-PACKAGES": "packages",
    "TEST-RERUN": "rerun",
    "TEST-PINS-KNOWN-BROKEN": "pins_known_broken",  # 'yes' marks intentional pin
}

REPEATING_KEYS = {
    "log_not", "log_contains",
    "sbl_contains", "sbl_not_contains", "sbl_count",
    "aux_contains", "aux_not_contains",
}


@dataclasses.dataclass
class Fixture:
    path: Path
    name: str
    what: str = ""
    source: str = ""
    section: str = ""
    exit_code: int = 0
    log_not: list = dataclasses.field(default_factory=list)
    log_contains: list = dataclasses.field(default_factory=list)
    sbl_contains: list = dataclasses.field(default_factory=list)
    sbl_not_contains: list = dataclasses.field(default_factory=list)
    sbl_count: list = dataclasses.field(default_factory=list)
    aux_contains: list = dataclasses.field(default_factory=list)
    aux_not_contains: list = dataclasses.field(default_factory=list)
    atoms_min: int = 0
    packages: list = dataclasses.field(default_factory=list)
    rerun: int = 2
    pins_known_broken: bool = False


def parse_fixture(path: Path) -> Fixture:
    """Parse the TEST-* header comment metadata from a .lvt file."""
    fix = Fixture(path=path, name=path.stem)
    header_re = re.compile(r"^%%\s+(TEST-[A-Z-]+):\s*(.*)$")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.startswith("%%"):
                # First non-metadata line ends the header. We allow blank
                # comment lines but stop on actual LaTeX content.
                if line.strip().startswith("\\") or not line.strip().startswith("%"):
                    break
                continue
            m = header_re.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip()
            attr = METADATA_KEYS.get(key)
            if attr is None:
                continue
            if attr == "exit_code":
                try:
                    fix.exit_code = int(value)
                except ValueError:
                    pass
            elif attr == "atoms_min":
                try:
                    fix.atoms_min = int(value)
                except ValueError:
                    pass
            elif attr == "rerun":
                try:
                    fix.rerun = int(value)
                except ValueError:
                    pass
            elif attr == "packages":
                fix.packages = [p.strip() for p in value.split(",") if p.strip()]
            elif attr == "pins_known_broken":
                fix.pins_known_broken = value.lower() in ("yes", "true", "1")
            elif attr in REPEATING_KEYS:
                getattr(fix, attr).append(value)
            else:
                setattr(fix, attr, value)
    return fix


# ----------------------------------------------------------------------
# Engine detection
# ----------------------------------------------------------------------


def detect_engine(name: str) -> Path | None:
    """Find a TeX engine binary on PATH. Returns absolute path or None."""
    p = shutil.which(name)
    return Path(p) if p else None


def assert_engine_available(engine: str) -> Path:
    bin_path = detect_engine(engine)
    if bin_path is None:
        sys.stderr.write(
            f"FATAL: {engine} not found on PATH.\n"
            f"This runner uses the system-wide TeX distribution per\n"
            f"user direction 2026-04-09. Install texlive-full system-wide\n"
            f"or run from inside `nix develop`.\n"
        )
        sys.exit(2)
    return bin_path


# ----------------------------------------------------------------------
# Run a single fixture
# ----------------------------------------------------------------------


@dataclasses.dataclass
class TestResult:
    fixture: Fixture
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    failures: list = dataclasses.field(default_factory=list)
    duration_ms: int = 0
    log_excerpt: str = ""


def run_fixture(fix: Fixture, engine_bin: Path, keep_temp: bool, verbose: bool) -> TestResult:
    """Compile a fixture and verify its assertions."""
    t0 = time.time()
    result = TestResult(fixture=fix, passed=False)

    if not STY_FILE.exists():
        result.skipped = True
        result.skip_reason = (
            f"semtex.sty not found at {STY_FILE} (implementation not landed yet)"
        )
        return result

    # Each fixture runs in its own temp dir so .aux/.sbl files don't collide.
    with tempfile.TemporaryDirectory(prefix=f"semtex-test-{fix.name}-") as tmp:
        tmp_path = Path(tmp)
        # Copy the fixture and the .sty into the temp dir.
        local_lvt = tmp_path / f"{fix.name}.tex"  # rename to .tex for engine
        shutil.copy(fix.path, local_lvt)
        shutil.copy(STY_FILE, tmp_path / "semtex.sty")
        if LTXML_FILE.exists():
            shutil.copy(LTXML_FILE, tmp_path / "semtex.ltxml")

        # Run the engine `rerun` times to populate .aux + .sbl.
        run_log = []
        for pass_num in range(1, fix.rerun + 1):
            cmd = [
                str(engine_bin),
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"{fix.name}.tex",
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                result.failures.append(f"pass {pass_num}: TIMEOUT after 120s")
                result.duration_ms = int((time.time() - t0) * 1000)
                return result
            run_log.append(("pass", pass_num, proc.returncode))
            if verbose:
                sys.stderr.write(f"  pass {pass_num}: exit {proc.returncode}\n")
            if proc.returncode != 0 and pass_num == fix.rerun:
                # Final pass failed; record exit code mismatch later.
                pass

        # Read artifacts.
        log_file = tmp_path / f"{fix.name}.log"
        aux_file = tmp_path / f"{fix.name}.aux"
        sbl_file = tmp_path / f"{fix.name}.sbl"

        log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
        aux_text = aux_file.read_text(encoding="utf-8", errors="replace") if aux_file.exists() else ""
        sbl_text = sbl_file.read_text(encoding="utf-8", errors="replace") if sbl_file.exists() else ""

        # ---- Assertions ----

        # 1. Exit code (use the LAST pass).
        last_exit = run_log[-1][2] if run_log else -1
        if last_exit != fix.exit_code:
            result.failures.append(
                f"exit code: expected {fix.exit_code}, got {last_exit}"
            )
            # Capture last 30 lines of log for the error excerpt.
            tail = log_text.splitlines()[-30:]
            result.log_excerpt = "\n".join(tail)

        # 2. log_not patterns.
        for pat in fix.log_not:
            if re.search(pat, log_text):
                result.failures.append(f"log matched forbidden pattern: {pat}")

        # 3. log_contains patterns.
        for pat in fix.log_contains:
            if not re.search(pat, log_text):
                result.failures.append(f"log missing required pattern: {pat}")

        # 4. SBL assertions.
        for s in fix.sbl_contains:
            if s not in sbl_text:
                result.failures.append(f"sbl missing required string: {s}")
        for s in fix.sbl_not_contains:
            if s in sbl_text:
                result.failures.append(f"sbl contains forbidden string: {s}")

        # 5. SBL counts: format "<pattern> = <n>".
        for spec in fix.sbl_count:
            try:
                pat, expected = spec.rsplit("=", 1)
                pat = pat.strip()
                expected_n = int(expected.strip())
            except ValueError:
                result.failures.append(f"malformed TEST-SBL-COUNT: {spec}")
                continue
            actual = sbl_text.count(pat)
            if actual != expected_n:
                result.failures.append(
                    f"sbl count for {pat!r}: expected {expected_n}, got {actual}"
                )

        # 6. AUX assertions.
        for s in fix.aux_contains:
            if s not in aux_text:
                result.failures.append(f"aux missing required string: {s}")
        for s in fix.aux_not_contains:
            if s in aux_text:
                result.failures.append(f"aux contains forbidden string: {s}")

        # 7. atoms_min: count \semtex@sbl@atom records.
        if fix.atoms_min > 0:
            atom_count = sbl_text.count("\\semtex@sbl@atom{")
            if atom_count < fix.atoms_min:
                result.failures.append(
                    f"atom count: expected >= {fix.atoms_min}, got {atom_count}"
                )

        if keep_temp:
            persistent = SCRIPT_DIR / "tmp" / fix.name
            persistent.parent.mkdir(parents=True, exist_ok=True)
            if persistent.exists():
                shutil.rmtree(persistent)
            shutil.copytree(tmp_path, persistent)

    result.passed = not result.failures
    result.duration_ms = int((time.time() - t0) * 1000)
    return result


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


def discover_fixtures(unit: bool, integration: bool, real_world: bool, pattern: str | None) -> list[Fixture]:
    fixtures = []
    dirs = []
    if unit:
        dirs.append(UNIT_DIR)
    if integration:
        dirs.append(INTEGRATION_DIR)
    if real_world:
        dirs.append(REAL_WORLD_DIR)
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.lvt")):
            if pattern and not re.search(pattern, path.name):
                continue
            try:
                fixtures.append(parse_fixture(path))
            except Exception as e:
                sys.stderr.write(f"WARN: failed to parse {path}: {e}\n")
    return fixtures


# ----------------------------------------------------------------------
# Summary output
# ----------------------------------------------------------------------


def summarize(results: list[TestResult], engine: str, verbose: bool) -> int:
    total = len(results)
    passed = sum(1 for r in results if r.passed and not r.skipped)
    failed = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    pinned_broken = sum(1 for r in results if r.fixture.pins_known_broken and not r.passed)

    print()
    print("=" * 72)
    print(f"semtex.sty test runner — engine: {engine}")
    print("=" * 72)

    # By-category breakdown.
    by_dir = defaultdict(lambda: [0, 0, 0])  # passed, failed, skipped
    for r in results:
        category = r.fixture.path.parent.name
        if r.skipped:
            by_dir[category][2] += 1
        elif r.passed:
            by_dir[category][0] += 1
        else:
            by_dir[category][1] += 1

    print()
    print("By category:")
    for cat, (p, f, s) in sorted(by_dir.items()):
        print(f"  {cat:20s}  pass={p:3d}  fail={f:3d}  skip={s:3d}")

    # Failed tests detail.
    if failed > 0:
        print()
        print("FAILED tests:")
        print("-" * 72)
        for r in results:
            if r.skipped or r.passed:
                continue
            marker = " (PINS-KNOWN-BROKEN)" if r.fixture.pins_known_broken else ""
            print(f"  {r.fixture.name}{marker}")
            print(f"    source: {r.fixture.source}")
            print(f"    what: {r.fixture.what}")
            for fail in r.failures:
                print(f"    FAIL: {fail}")
            if r.log_excerpt and verbose:
                print("    log tail:")
                print(textwrap.indent(r.log_excerpt, "      "))
        print("-" * 72)

    # Skipped tests (typically: semtex.sty not yet implemented).
    if skipped > 0:
        print()
        print(f"SKIPPED ({skipped}):")
        for r in results:
            if r.skipped:
                print(f"  {r.fixture.name}: {r.skip_reason}")

    print()
    print("=" * 72)
    print(
        f"TOTAL: {total}  passed={passed}  failed={failed}  "
        f"skipped={skipped}  pinned-broken={pinned_broken}"
    )
    print("=" * 72)

    if pinned_broken > 0:
        print(
            f"\nNOTE: {pinned_broken} test(s) intentionally pin known-broken "
            f"behaviour (TEST-PINS-KNOWN-BROKEN: yes). They are reported as "
            f"FAILED in the summary but do NOT contribute to the runner's "
            f"exit code. They flag intentional hazards documented in the "
            f"design (e.g. equations=shared mode), and will need to be "
            f"rewritten when the underlying issue is fixed."
        )

    # Exit code: non-zero only on real failures.
    real_failures = failed - pinned_broken
    return 0 if real_failures == 0 else 1


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="run-tests.py",
        description="semtex.sty test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--filter", help="regex; only run fixtures whose name matches")
    parser.add_argument(
        "--engine",
        choices=["pdflatex", "lualatex", "xelatex"],
        default="pdflatex",
        help="TeX engine to use (default: pdflatex)",
    )
    parser.add_argument("--keep-temp", action="store_true", help="copy temp dirs to testfiles/tmp/<name>/ for inspection")
    parser.add_argument("--verbose", "-v", action="store_true", help="show pass-by-pass output and log tails")
    parser.add_argument("--unit-only", action="store_true", help="only run unit fixtures")
    parser.add_argument("--integration-only", action="store_true", help="only run integration fixtures")
    parser.add_argument("--real-world", action="store_true", help="include real-world arxiv-corpus fixtures")
    args = parser.parse_args()

    # Engine binary.
    engine_bin = assert_engine_available(args.engine)

    # System TeX notice.
    sys.stderr.write(
        f"semtex.sty test runner — using system TeX: {engine_bin}\n"
        f"NOTE: per user direction 2026-04-09, the project's Nix flake does\n"
        f"      not yet include all required packages. System-wide texlive-full\n"
        f"      is in use as a one-time exception. Future runs should go\n"
        f"      through `nix develop` once the flake is updated.\n\n"
    )

    # Discover fixtures.
    if args.unit_only:
        unit, integration, real_world = True, False, False
    elif args.integration_only:
        unit, integration, real_world = False, True, False
    else:
        unit, integration = True, True
        real_world = args.real_world

    fixtures = discover_fixtures(unit, integration, real_world, args.filter)

    if not fixtures:
        sys.stderr.write("No fixtures matched the filter.\n")
        return 0

    sys.stderr.write(f"Discovered {len(fixtures)} fixture(s)\n\n")

    # Run.
    results = []
    for fix in fixtures:
        sys.stderr.write(f"  {fix.name} ...")
        sys.stderr.flush()
        result = run_fixture(fix, engine_bin, args.keep_temp, args.verbose)
        if result.skipped:
            sys.stderr.write(" SKIP\n")
        elif result.passed:
            sys.stderr.write(f" PASS ({result.duration_ms}ms)\n")
        else:
            marker = " [PINS-KNOWN-BROKEN]" if fix.pins_known_broken else ""
            sys.stderr.write(f" FAIL{marker} ({result.duration_ms}ms)\n")
        results.append(result)

    return summarize(results, args.engine, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
