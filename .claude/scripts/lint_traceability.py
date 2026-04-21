#!/usr/bin/env python3
"""
lint_traceability.py -- Behavioral traceability linter for codependent.

ENFORCES:
  1. Every macro definition must be classified: @behavior, @implements, or @utility.
     Unclassified macros are ERRORs unless listed in .traceability-baseline.
  2. Every docs/BEHAVIOR.md [B-XXX] statement must have at least one @behavior tag.
     Uncovered statements are ERRORs unless listed in .traceability-baseline.
  3. Every @behavior tag must reference a real docs/BEHAVIOR.md ID.
  4. Every @implements must reference a macro with @behavior tags.
  5. No macro has BOTH @behavior and @implements.

Exit codes:
  0 -- all checks pass
  1 -- errors found

Usage:
  python3 lint_traceability.py                        # full check
  python3 lint_traceability.py --changed-file F.sty   # report affected behaviors
  python3 lint_traceability.py --update-baseline       # regenerate baseline from current state
"""

import glob
import json
import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


# ---------------------------------------------------------------------------
# Constants (paths resolved via .claude/paths.toml)
# ---------------------------------------------------------------------------

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with open(os.path.join(PROJ_ROOT, ".claude", "paths.toml"), "rb") as _f:
    _PATHS = tomllib.load(_f)

BEHAVIOR_MD = os.path.join(PROJ_ROOT, _PATHS["docs"]["behavior"])
BASELINE_FILE = os.path.join(PROJ_ROOT, _PATHS["docs"]["traceability_baseline"])
TEST_BEHAVIOR_BASELINE = os.path.join(PROJ_ROOT, _PATHS["tests"]["behavior_baseline"])
STY_FILES = [
    os.path.join(PROJ_ROOT, "codependent.sty"),
    os.path.join(PROJ_ROOT, "codependent-render.sty"),
]
TEST_DIRS = [
    os.path.join(PROJ_ROOT, "testfiles", "unit"),
    os.path.join(PROJ_ROOT, "testfiles", "integration"),
]

RE_BEHAVIOR_ID = re.compile(r'\[B-([A-Z0-9]+(?:-[A-Z0-9]+)*)\]')
RE_STY_BEHAVIOR = re.compile(r'^%%\s+@behavior\s+(B-[A-Z0-9]+(?:-[A-Z0-9]+)*)')
RE_STY_IMPLEMENTS = re.compile(r'^%%\s+@implements\s+(\\[a-zA-Z@]+)')
RE_STY_UTILITY = re.compile(r'^%%\s+@utility\b')

RE_MACRO_DEF = re.compile(
    r'\\(?:def|newcommand|renewcommand|NewDocumentCommand|RenewDocumentCommand'
    r'|DeclareDocumentCommand|ProvideDocumentCommand'
    r'|newcommand\*|renewcommand\*'
    r'|long\s*\\def|gdef|edef|xdef)'
    r'\s*\{?\s*(\\[a-zA-Z@]+)'
)
RE_PLAIN_DEF = re.compile(r'\\(?:def|gdef|edef|xdef)\s*(\\[a-zA-Z@]+)')


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def load_baseline(path: str) -> Tuple[Set[str], Set[str]]:
    """Load .traceability-baseline. Returns (unclassified_macros, uncovered_bids)."""
    macros: Set[str] = set()
    bids: Set[str] = set()
    if not os.path.isfile(path):
        return macros, bids
    with open(path, "r", encoding="utf-8") as f:
        section = None
        for line in f:
            line = line.strip()
            if line == "# unclassified-macros":
                section = "macros"
                continue
            elif line == "# uncovered-behaviors":
                section = "bids"
                continue
            elif line.startswith("#") or not line:
                continue
            if section == "macros":
                macros.add(line)
            elif section == "bids":
                bids.add(line)
    return macros, bids


def write_baseline(path: str, unclassified: Set[str], uncovered: Set[str]) -> None:
    """Write .traceability-baseline from current state."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Traceability baseline — pre-rewrite unclassified macros and uncovered behaviors.\n")
        f.write("# This file shrinks with each Phase 3 wave. Empty = 100% coverage.\n")
        f.write("# Regenerate: python3 .claude/scripts/lint_traceability.py --update-baseline\n\n")
        f.write("# unclassified-macros\n")
        for m in sorted(unclassified):
            f.write(f"{m}\n")
        f.write("\n# uncovered-behaviors\n")
        for b in sorted(uncovered):
            f.write(f"{b}\n")


# ---------------------------------------------------------------------------
# docs/BEHAVIOR.md parser
# ---------------------------------------------------------------------------

def parse_behavior_md(path: str) -> Dict[str, str]:
    """Parse docs/BEHAVIOR.md, return {id: description} for every [B-XXX-YYY] tag."""
    specs: Dict[str, str] = {}
    if not os.path.isfile(path):
        print(f"WARNING: {path} not found", file=sys.stderr)
        return specs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = RE_BEHAVIOR_ID.search(line)
            if m:
                bid = "B-" + m.group(1)
                rest = line[m.end():].strip().lstrip("|").strip()
                if "|" in rest:
                    rest = rest[:rest.index("|")].strip()
                if not rest:
                    rest = "(no description)"
                specs[bid] = rest
    return specs


# ---------------------------------------------------------------------------
# .sty parser — finds ALL macro definitions AND their tags
# ---------------------------------------------------------------------------

class MacroInfo:
    def __init__(self, name: str, filename: str, line: int):
        self.name = name
        self.filename = filename
        self.line = line
        self.behavior_ids: List[str] = []
        self.implements: List[str] = []
        self.is_utility: bool = False

    @property
    def is_classified(self) -> bool:
        return bool(self.behavior_ids) or bool(self.implements) or self.is_utility


def _extract_macro_name(line: str) -> Optional[str]:
    if not line or line.startswith("%"):
        return None
    for pattern in [RE_MACRO_DEF, RE_PLAIN_DEF]:
        m = pattern.search(line)
        if m:
            return m.group(1)
    return None


def _count_braces(line: str) -> int:
    """Count net brace depth change for a line, ignoring \\{ \\} and comments."""
    depth = 0
    i = 0
    while i < len(line):
        c = line[i]
        if c == '%':
            break  # rest is comment
        if c == '\\' and i + 1 < len(line):
            i += 2  # skip escaped char (\{ \} \% etc.)
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return depth


def parse_sty_file(path: str) -> List[MacroInfo]:
    """Parse a .sty file. Returns only TOP-LEVEL macros (brace depth 0) with their tags."""
    if not os.path.isfile(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    macros: List[MacroInfo] = []
    errors: List[str] = []
    pending_behaviors: List[str] = []
    pending_implements: List[str] = []
    pending_utility: bool = False
    brace_depth: int = 0

    basename = os.path.basename(path)

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Only collect tags at brace depth 0 (top level)
        if brace_depth == 0:
            m_beh = RE_STY_BEHAVIOR.match(stripped)
            if m_beh:
                pending_behaviors.append(m_beh.group(1))
                continue

            m_impl = RE_STY_IMPLEMENTS.match(stripped)
            if m_impl:
                pending_implements.append(m_impl.group(1))
                continue

            m_util = RE_STY_UTILITY.match(stripped)
            if m_util:
                pending_utility = True
                continue

        # Check for macro definition ONLY at brace depth 0
        if brace_depth == 0:
            macro_name = _extract_macro_name(stripped)
            if macro_name:
                info = MacroInfo(macro_name, basename, lineno)
                info.behavior_ids = pending_behaviors[:]
                info.implements = pending_implements[:]
                info.is_utility = pending_utility
                macros.append(info)
                pending_behaviors.clear()
                pending_implements.clear()
                pending_utility = False

        # Track brace depth
        brace_depth += _count_braces(line)
        if brace_depth < 0:
            brace_depth = 0  # malformed input recovery

    # Orphaned tags at EOF
    if pending_behaviors or pending_implements or pending_utility:
        tags = []
        if pending_behaviors:
            tags.extend(f"@behavior {b}" for b in pending_behaviors)
        if pending_implements:
            tags.extend(f"@implements {i}" for i in pending_implements)
        if pending_utility:
            tags.append("@utility")
        # Store as a pseudo-macro so the error is caught
        info = MacroInfo("(orphaned-tags-at-EOF)", basename, len(lines))
        info.behavior_ids = pending_behaviors[:]
        info.implements = pending_implements[:]
        info.is_utility = pending_utility
        macros.append(info)

    return macros


# ---------------------------------------------------------------------------
# Test-behavior linting (.lvt TEST-BEHAVIOR headers)
# ---------------------------------------------------------------------------

RE_TEST_BEHAVIOR = re.compile(r'^%%\s+TEST-BEHAVIOR:\s*(.+)$')
RE_TEST_SOURCE_OR_SECTION = re.compile(r'^%%\s+TEST-(?:SOURCE|SECTION):\s*(.+)$')
# Only flag refs to docs/BEHAVIOR.md in TEST-SOURCE/TEST-SECTION: those should
# use %% TEST-BEHAVIOR: B-XXX instead of prose section citations.
# docs/DESIGN.md, docs/CONVENTIONS.md etc. are legitimate source pointers.
RE_PROSE_DOC_REF = re.compile(r'\bdocs/BEHAVIOR\.md\b')


def load_test_behavior_baseline(path: str) -> Set[str]:
    """Grandfather list of .lvt files (relative to PROJ_ROOT) exempt from the rule."""
    exempt: Set[str] = set()
    if not os.path.isfile(path):
        return exempt
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            exempt.add(line)
    return exempt


def parse_lvt_header(path: str) -> Tuple[List[str], List[Tuple[int, str]]]:
    """Return (behavior_ids, [(lineno, raw_line_with_prose_docref), ...]).

    Reads the `%%` header block until the first non-header line.
    """
    ids: List[str] = []
    prose_refs: List[Tuple[int, str]] = []
    if not os.path.isfile(path):
        return ids, prose_refs
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.startswith("%%"):
                stripped = line.strip()
                if stripped and not stripped.startswith("%"):
                    break  # end of header
                continue
            m = RE_TEST_BEHAVIOR.match(line)
            if m:
                for tok in m.group(1).split(","):
                    tok = tok.strip()
                    if tok:
                        ids.append(tok)
                continue
            m = RE_TEST_SOURCE_OR_SECTION.match(line)
            if m and RE_PROSE_DOC_REF.search(m.group(1)):
                prose_refs.append((lineno, line))
    return ids, prose_refs


def find_lvt_files() -> List[str]:
    out: List[str] = []
    for d in TEST_DIRS:
        for p in sorted(glob.glob(os.path.join(d, "*.lvt"))):
            out.append(p)
    return out


def check_tests(specs: Dict[str, str]) -> List[str]:
    """Return error strings. Empty = pass."""
    errors: List[str] = []
    exempt = load_test_behavior_baseline(TEST_BEHAVIOR_BASELINE)
    for lvt in find_lvt_files():
        rel = os.path.relpath(lvt, PROJ_ROOT)
        ids, prose_refs = parse_lvt_header(lvt)
        if rel in exempt:
            continue
        if not ids:
            errors.append(f"{rel}: missing TEST-BEHAVIOR: header (add ≥1 B-* ID from docs/BEHAVIOR.md or add to .test-behavior-baseline)")
        for bid in ids:
            if bid not in specs:
                errors.append(f"{rel}: TEST-BEHAVIOR references unknown ID {bid!r}")
        for lineno, line in prose_refs:
            errors.append(f"{rel}:{lineno}: prose docs/*.md ref in TEST-SOURCE/TEST-SECTION header — cite B-* IDs via TEST-BEHAVIOR instead ({line.strip()})")
    return errors


# ---------------------------------------------------------------------------
# Full check
# ---------------------------------------------------------------------------

def run_full_check() -> int:
    specs = parse_behavior_md(BEHAVIOR_MD)
    baseline_macros, baseline_bids = load_baseline(BASELINE_FILE)

    all_macros: List[MacroInfo] = []
    for sty in STY_FILES:
        all_macros.extend(parse_sty_file(sty))

    # Build lookups
    id_to_macros: Dict[str, List[MacroInfo]] = {}
    name_to_macro: Dict[str, MacroInfo] = {}
    for mi in all_macros:
        name_to_macro[mi.name] = mi
        for bid in mi.behavior_ids:
            id_to_macros.setdefault(bid, []).append(mi)

    errors: List[str] = []

    # Check 1: Every @behavior tag references a real docs/BEHAVIOR.md ID
    for mi in all_macros:
        for bid in mi.behavior_ids:
            if bid not in specs:
                errors.append(f"@behavior {bid} in {mi.name} ({mi.filename}:{mi.line}): nonexistent spec ID")

    # Check 2: Every @implements references a macro with @behavior tags
    for mi in all_macros:
        for impl_ref in mi.implements:
            target = name_to_macro.get(impl_ref)
            if target is None or not target.behavior_ids:
                errors.append(f"@implements {impl_ref} in {mi.name} ({mi.filename}:{mi.line}): target has no @behavior tags")

    # Check 3: No macro has BOTH @behavior and @implements
    for mi in all_macros:
        if mi.behavior_ids and mi.implements:
            errors.append(f"{mi.name} ({mi.filename}:{mi.line}): has both @behavior and @implements")

    # Check 4: Every macro must be classified (unless in baseline)
    unclassified = []
    for mi in all_macros:
        if not mi.is_classified and mi.name not in baseline_macros:
            unclassified.append(mi)
            errors.append(f"{mi.name} ({mi.filename}:{mi.line}): UNCLASSIFIED — must have @behavior, @implements, or @utility")

    # Check 5: Every behavioral statement must be covered (unless in baseline)
    covered_ids: Set[str] = set()
    for mi in all_macros:
        for bid in mi.behavior_ids:
            if bid in specs:
                covered_ids.add(bid)

    uncovered_ids = sorted(set(specs.keys()) - covered_ids)
    new_uncovered = [bid for bid in uncovered_ids if bid not in baseline_bids]
    if new_uncovered:
        for bid in new_uncovered:
            desc = specs[bid]
            if len(desc) > 60:
                desc = desc[:57] + "..."
            errors.append(f"UNCOVERED {bid}: {desc}")

    # Check 6: Baseline entries that are now covered/classified should be removed
    stale_baseline_macros = [m for m in baseline_macros if m in name_to_macro and name_to_macro[m].is_classified]
    stale_baseline_bids = [b for b in baseline_bids if b in covered_ids]

    # Check 7: Test-to-behavior linkage (.lvt TEST-BEHAVIOR headers)
    test_errors = check_tests(specs)
    errors.extend(test_errors)

    # Stats
    n_total_macros = len(all_macros)
    n_classified = sum(1 for mi in all_macros if mi.is_classified)
    n_baseline_macros = sum(1 for mi in all_macros if not mi.is_classified and mi.name in baseline_macros)
    n_specs = len(specs)
    n_covered = len(covered_ids)
    n_baseline_bids = len([b for b in uncovered_ids if b in baseline_bids])

    # Test-behavior stats
    all_lvt = find_lvt_files()
    test_exempt = load_test_behavior_baseline(TEST_BEHAVIOR_BASELINE)
    n_tests = len(all_lvt)
    n_tests_assigned = 0
    for p in all_lvt:
        rel = os.path.relpath(p, PROJ_ROOT)
        if rel in test_exempt:
            continue
        tids, _ = parse_lvt_header(p)
        if tids:
            n_tests_assigned += 1
    n_tests_exempt = sum(1 for p in all_lvt if os.path.relpath(p, PROJ_ROOT) in test_exempt)

    # Output
    print("=== Behavioral Traceability ===")
    print(f"docs/BEHAVIOR.md: {n_specs} behavioral statements")
    print(f"Macros: {n_total_macros} total, {n_classified} classified, {n_baseline_macros} baselined, {len(unclassified)} unclassified")
    print(f"Coverage: {n_covered}/{n_specs} statements covered ({n_covered/n_specs*100:.0f}%), {n_baseline_bids} baselined")
    print(f"Tests: {n_tests} total, {n_tests_assigned} with TEST-BEHAVIOR, {n_tests_exempt} baselined")
    print()

    if stale_baseline_macros or stale_baseline_bids:
        print("STALE BASELINE (remove these — they're now classified/covered):")
        for m in sorted(stale_baseline_macros):
            print(f"  macro: {m}")
        for b in sorted(stale_baseline_bids):
            print(f"  behavior: {b}")
        print()

    # Ratchet check — runs on every full invocation
    print("=== Baseline Ratchet ===")
    ratchet_rc = run_check_ratchet()
    print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
        print()
        if ratchet_rc != 0:
            print(f"RESULT: FAIL ({len(errors)} traceability errors + ratchet fail)")
        else:
            print(f"RESULT: FAIL ({len(errors)} errors)")
        return 1
    elif ratchet_rc != 0:
        print("RESULT: FAIL (ratchet)")
        return 1
    else:
        print("RESULT: PASS")
        return 0


# ---------------------------------------------------------------------------
# Changed-file mode
# ---------------------------------------------------------------------------

def run_changed_file(filepath: str) -> int:
    if not filepath.endswith(".sty") or not os.path.isfile(filepath):
        return 0

    macros = parse_sty_file(filepath)
    affected_ids: Set[str] = set()
    name_to_macro: Dict[str, MacroInfo] = {}
    for mi in macros:
        name_to_macro[mi.name] = mi
        affected_ids.update(mi.behavior_ids)
    for mi in macros:
        for impl_ref in mi.implements:
            target = name_to_macro.get(impl_ref)
            if target:
                affected_ids.update(target.behavior_ids)

    if affected_ids:
        specs = parse_behavior_md(BEHAVIOR_MD)
        print(f"Edit touches code implementing: {', '.join(sorted(affected_ids))}")
        print("  — verify docs/BEHAVIOR.md still matches.")

    # Check for unclassified macros in the edited file
    baseline_macros, _ = load_baseline(BASELINE_FILE)
    new_unclassified = [mi for mi in macros if not mi.is_classified and mi.name not in baseline_macros]
    if new_unclassified:
        print(f"UNCLASSIFIED macros (must add @behavior/@implements/@utility):")
        for mi in new_unclassified:
            print(f"  {mi.name} ({mi.filename}:{mi.line})")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Baseline ratchet
# ---------------------------------------------------------------------------

BASELINE_SIZES_FILE = os.path.join(PROJ_ROOT, ".claude", "baseline-sizes.json")

# Keys: must match what compute_baseline_sizes() returns
RATCHET_KEYS = (
    ".traceability-baseline.unclassified_macros",
    ".traceability-baseline.uncovered_behaviors",
    ".test-behavior-baseline",
)


def _count_traceability_baseline_sections(path: str) -> tuple:
    """Return (n_macros, n_bids) — entry counts in each section."""
    macros, bids = load_baseline(path)
    return len(macros), len(bids)


def compute_baseline_sizes() -> Dict[str, int]:
    n_macros, n_bids = _count_traceability_baseline_sections(BASELINE_FILE)
    exempt = load_test_behavior_baseline(TEST_BEHAVIOR_BASELINE)
    return {
        ".traceability-baseline.unclassified_macros": n_macros,
        ".traceability-baseline.uncovered_behaviors": n_bids,
        ".test-behavior-baseline": len(exempt),
    }


def load_baseline_sizes() -> Dict[str, int]:
    if not os.path.isfile(BASELINE_SIZES_FILE):
        return {}
    with open(BASELINE_SIZES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_baseline_sizes(sizes: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(BASELINE_SIZES_FILE), exist_ok=True)
    with open(BASELINE_SIZES_FILE, "w", encoding="utf-8") as f:
        json.dump(sizes, f, indent=2, sort_keys=True)
        f.write("\n")


def run_check_ratchet() -> int:
    """Check that no baseline has grown. Return 0 = pass, 1 = fail."""
    recorded = load_baseline_sizes()
    if not recorded:
        print("ERROR: .claude/baseline-sizes.json not found — run --update-ratchet first", file=sys.stderr)
        return 1
    current = compute_baseline_sizes()
    errors = []
    for key in RATCHET_KEYS:
        cur = current.get(key, 0)
        rec = recorded.get(key, 0)
        if cur > rec:
            errors.append(f"  GREW: {key}: {rec} → {cur} (+{cur - rec})")
        elif cur < rec:
            print(f"  shrunk: {key}: {rec} → {cur} (−{rec - cur}) — run --update-ratchet")
        else:
            print(f"  ok:     {key}: {cur}")
    if errors:
        print("RATCHET FAIL — baselines must only shrink:")
        for e in errors:
            print(e)
        return 1
    return 0


def run_update_ratchet() -> int:
    """Write current baseline sizes to .claude/baseline-sizes.json."""
    sizes = compute_baseline_sizes()
    write_baseline_sizes(sizes)
    print(f"Ratchet updated → {BASELINE_SIZES_FILE}")
    for key, val in sorted(sizes.items()):
        print(f"  {key}: {val}")
    return 0


# ---------------------------------------------------------------------------
# Update baseline
# ---------------------------------------------------------------------------

def run_update_baseline() -> int:
    specs = parse_behavior_md(BEHAVIOR_MD)
    all_macros: List[MacroInfo] = []
    for sty in STY_FILES:
        all_macros.extend(parse_sty_file(sty))

    unclassified = {mi.name for mi in all_macros if not mi.is_classified}

    covered_ids: Set[str] = set()
    for mi in all_macros:
        for bid in mi.behavior_ids:
            if bid in specs:
                covered_ids.add(bid)
    uncovered = set(specs.keys()) - covered_ids

    write_baseline(BASELINE_FILE, unclassified, uncovered)
    print(f"Baseline written to {BASELINE_FILE}")
    print(f"  {len(unclassified)} unclassified macros")
    print(f"  {len(uncovered)} uncovered behavioral statements")
    print(f"Phase 3 goal: reduce both to 0.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = sys.argv[1:]

    if "--update-baseline" in args:
        return run_update_baseline()

    if "--update-ratchet" in args:
        return run_update_ratchet()

    if "--check-ratchet" in args:
        return run_check_ratchet()

    if "--changed-file" in args:
        idx = args.index("--changed-file")
        if idx + 1 < len(args):
            return run_changed_file(args[idx + 1])
        else:
            print("ERROR: --changed-file requires a file path", file=sys.stderr)
            return 1

    return run_full_check()


if __name__ == "__main__":
    sys.exit(main())
