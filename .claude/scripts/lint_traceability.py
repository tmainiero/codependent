#!/usr/bin/env python3
"""
lint_traceability.py -- Behavioral traceability linter for codependent.

ENFORCES:
  1. Every macro definition must be classified: @behavior, @implements, or @utility.
     Unclassified macros are ERRORs unless listed in .traceability-baseline.
  2. Every BEHAVIOR.md [B-XXX] statement must have at least one @behavior tag.
     Uncovered statements are ERRORs unless listed in .traceability-baseline.
  3. Every @behavior tag must reference a real BEHAVIOR.md ID.
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

import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BEHAVIOR_MD = os.path.join(PROJ_ROOT, "BEHAVIOR.md")
BASELINE_FILE = os.path.join(PROJ_ROOT, ".traceability-baseline")
STY_FILES = [
    os.path.join(PROJ_ROOT, "codependent.sty"),
    os.path.join(PROJ_ROOT, "codependent-render.sty"),
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
# BEHAVIOR.md parser
# ---------------------------------------------------------------------------

def parse_behavior_md(path: str) -> Dict[str, str]:
    """Parse BEHAVIOR.md, return {id: description} for every [B-XXX-YYY] tag."""
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


def parse_sty_file(path: str) -> List[MacroInfo]:
    """Parse a .sty file. Returns ALL macros with their tags (or no tags)."""
    if not os.path.isfile(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    macros: List[MacroInfo] = []
    pending_behaviors: List[str] = []
    pending_implements: List[str] = []
    pending_utility: bool = False

    basename = os.path.basename(path)

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Collect tags
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

        # Check for macro definition
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

    return macros


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

    # Check 1: Every @behavior tag references a real BEHAVIOR.md ID
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

    # Stats
    n_total_macros = len(all_macros)
    n_classified = sum(1 for mi in all_macros if mi.is_classified)
    n_baseline_macros = sum(1 for mi in all_macros if not mi.is_classified and mi.name in baseline_macros)
    n_specs = len(specs)
    n_covered = len(covered_ids)
    n_baseline_bids = len([b for b in uncovered_ids if b in baseline_bids])

    # Output
    print("=== Behavioral Traceability ===")
    print(f"BEHAVIOR.md: {n_specs} behavioral statements")
    print(f"Macros: {n_total_macros} total, {n_classified} classified, {n_baseline_macros} baselined, {len(unclassified)} unclassified")
    print(f"Coverage: {n_covered}/{n_specs} statements covered ({n_covered/n_specs*100:.0f}%), {n_baseline_bids} baselined")
    print()

    if stale_baseline_macros or stale_baseline_bids:
        print("STALE BASELINE (remove these — they're now classified/covered):")
        for m in sorted(stale_baseline_macros):
            print(f"  macro: {m}")
        for b in sorted(stale_baseline_bids):
            print(f"  behavior: {b}")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
        print()
        print(f"RESULT: FAIL ({len(errors)} errors)")
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
        print("  — verify BEHAVIOR.md still matches.")

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
