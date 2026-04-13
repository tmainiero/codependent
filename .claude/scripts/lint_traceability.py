#!/usr/bin/env python3
"""
lint_traceability.py -- Behavioral traceability linter for codependent.

Parses BEHAVIOR.md for behavioral statement IDs ([B-XXX-YYY]) and .sty files
for @behavior / @implements / @utility tags.  Checks cross-references and
reports coverage.

Checks:
  1. Every BEHAVIOR.md ID has at least one @behavior tag in the code
     (reported as UNCOVERED, not an error -- coverage improves over time)
  2. Every @behavior tag references a real BEHAVIOR.md ID (ERROR)
  3. Every @implements \\foo references a macro that has @behavior tags (ERROR)
  4. No macro has BOTH @behavior and @implements (ERROR)
  5. Coverage summary

Exit codes:
  0 -- no errors (low coverage is OK)
  1 -- errors found (stale tags, broken references)

Usage:
  python3 lint_traceability.py                        # full check
  python3 lint_traceability.py --changed-file F.sty   # report affected behaviors
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
STY_FILES = [
    os.path.join(PROJ_ROOT, "codependent.sty"),
    os.path.join(PROJ_ROOT, "codependent-render.sty"),
]

# Regex for behavior IDs in BEHAVIOR.md: [B-SECTION-ITEM] at start of a
# table cell or bullet point.  Captures the ID and the rest of the line
# as the description.
RE_BEHAVIOR_ID = re.compile(r'\[B-([A-Z0-9]+(?:-[A-Z0-9]+)*)\]')

# Regex for @behavior tags in .sty comment lines: %% @behavior B-XXX-YYY
RE_STY_BEHAVIOR = re.compile(r'^%%\s+@behavior\s+(B-[A-Z0-9]+(?:-[A-Z0-9]+)*)')

# Regex for @implements tags: %% @implements \macro@name
RE_STY_IMPLEMENTS = re.compile(r'^%%\s+@implements\s+(\\[a-zA-Z@]+)')

# Regex for @utility tags: %% @utility
RE_STY_UTILITY = re.compile(r'^%%\s+@utility\b')

# Regex for macro definitions (the "next macro" after a tag block)
RE_MACRO_DEF = re.compile(
    r'\\(?:def|newcommand|renewcommand|NewDocumentCommand|RenewDocumentCommand'
    r'|DeclareDocumentCommand|ProvideDocumentCommand'
    r'|newcommand\*|renewcommand\*'
    r'|long\s*\\def|gdef|edef|xdef)'
    r'\s*\{?\s*(\\[a-zA-Z@]+)'
)

# Also match \cs_new:Npn style and plain \def\macro
RE_MACRO_DEF_ALT = re.compile(
    r'\\(?:cs_new(?:_protected)?(?:_nopar)?:Npn)\s+(\\[a-zA-Z@_:]+)'
)

RE_PLAIN_DEF = re.compile(
    r'\\(?:def|gdef|edef|xdef)\s*(\\[a-zA-Z@]+)'
)


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
                # Extract description: everything after the [B-XXX] tag on the line,
                # stripping markdown table separators and leading/trailing whitespace.
                rest = line[m.end():].strip()
                # Remove leading pipe if in a table row
                rest = rest.lstrip("|").strip()
                # Truncate at next pipe (for table rows with multiple columns)
                if "|" in rest:
                    rest = rest[:rest.index("|")].strip()
                # For bullet points, the description is the rest of the line
                if not rest:
                    # Try to get something from before the ID
                    rest = "(no description)"
                specs[bid] = rest
    return specs


# ---------------------------------------------------------------------------
# .sty file parser
# ---------------------------------------------------------------------------

class MacroInfo:
    """Collected tag information for a single macro."""
    def __init__(self, name: str, filename: str, line: int):
        self.name = name
        self.filename = filename
        self.line = line
        self.behavior_ids: List[str] = []
        self.implements: List[str] = []
        self.is_utility: bool = False


def parse_sty_file(path: str) -> Tuple[List[MacroInfo], int, int, int]:
    """
    Parse a .sty file for @behavior, @implements, @utility tags.

    Returns (macros, behavior_count, implements_count, utility_count).
    Each macro in the list has its tags attached.  Tags accumulate in a
    pending buffer until a macro definition line is encountered.
    """
    macros: List[MacroInfo] = []
    behavior_count = 0
    implements_count = 0
    utility_count = 0

    if not os.path.isfile(path):
        return macros, 0, 0, 0

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Pending tags accumulate until the next macro definition
    pending_behaviors: List[str] = []
    pending_implements: List[str] = []
    pending_utility: bool = False
    pending_start_line: Optional[int] = None

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Check for tag lines (must be %% comment lines)
        m_beh = RE_STY_BEHAVIOR.match(stripped)
        if m_beh:
            bid = m_beh.group(1)
            pending_behaviors.append(bid)
            behavior_count += 1
            if pending_start_line is None:
                pending_start_line = lineno
            continue

        m_impl = RE_STY_IMPLEMENTS.match(stripped)
        if m_impl:
            macro_ref = m_impl.group(1)
            pending_implements.append(macro_ref)
            implements_count += 1
            if pending_start_line is None:
                pending_start_line = lineno
            continue

        m_util = RE_STY_UTILITY.match(stripped)
        if m_util:
            pending_utility = True
            utility_count += 1
            if pending_start_line is None:
                pending_start_line = lineno
            continue

        # If we have pending tags, look for a macro definition
        if pending_behaviors or pending_implements or pending_utility:
            macro_name = _extract_macro_name(stripped)
            if macro_name:
                info = MacroInfo(macro_name, os.path.basename(path), lineno)
                info.behavior_ids = pending_behaviors[:]
                info.implements = pending_implements[:]
                info.is_utility = pending_utility
                macros.append(info)
                pending_behaviors.clear()
                pending_implements.clear()
                pending_utility = False
                pending_start_line = None
            # If the line is not a comment and not blank, and we have pending
            # tags but no macro def found, keep accumulating (tags might span
            # multiple comment lines before the def).  But if it's a non-comment,
            # non-blank, non-tag line that's also not a macro def, the tags are
            # orphaned -- we still attach them when the next macro appears.

    # Handle any orphaned pending tags at EOF (shouldn't happen in well-formed code)
    if pending_behaviors or pending_implements or pending_utility:
        info = MacroInfo("(orphaned-at-EOF)", os.path.basename(path),
                         pending_start_line or len(lines))
        info.behavior_ids = pending_behaviors[:]
        info.implements = pending_implements[:]
        info.is_utility = pending_utility
        macros.append(info)

    return macros, behavior_count, implements_count, utility_count


def _extract_macro_name(line: str) -> Optional[str]:
    """Try to extract a macro name from a definition line."""
    # Skip pure comment lines and blank lines
    if not line or line.startswith("%"):
        return None

    for pattern in [RE_MACRO_DEF, RE_MACRO_DEF_ALT, RE_PLAIN_DEF]:
        m = pattern.search(line)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Full check mode
# ---------------------------------------------------------------------------

def run_full_check() -> int:
    """Run the full traceability check.  Returns exit code."""
    specs = parse_behavior_md(BEHAVIOR_MD)

    all_macros: List[MacroInfo] = []
    total_behavior = 0
    total_implements = 0
    total_utility = 0
    file_reports: List[str] = []

    for sty in STY_FILES:
        if not os.path.isfile(sty):
            continue
        macros, bc, ic, uc = parse_sty_file(sty)
        all_macros.extend(macros)
        total_behavior += bc
        total_implements += ic
        total_utility += uc
        file_reports.append(
            f"  {os.path.basename(sty)}: {bc} @behavior tags, "
            f"{ic} @implements tags, {uc} @utility tags"
        )

    # Build lookup structures
    # behavior_id -> list of macros implementing it
    id_to_macros: Dict[str, List[MacroInfo]] = {}
    # macro_name -> MacroInfo (for @implements lookups)
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
                errors.append(
                    f"@behavior {bid} in {mi.name}: nonexistent spec ID"
                )

    # Check 2: Every @implements \foo references a macro with @behavior tags
    for mi in all_macros:
        for impl_ref in mi.implements:
            target = name_to_macro.get(impl_ref)
            if target is None or not target.behavior_ids:
                errors.append(
                    f"@implements {impl_ref} but {impl_ref} has no @behavior tags"
                )

    # Check 3: No macro has BOTH @behavior and @implements
    for mi in all_macros:
        if mi.behavior_ids and mi.implements:
            errors.append(
                f"{mi.name} has both @behavior and @implements"
            )

    # Coverage
    covered_ids: Set[str] = set()
    for mi in all_macros:
        for bid in mi.behavior_ids:
            if bid in specs:
                covered_ids.add(bid)

    uncovered_ids = sorted(set(specs.keys()) - covered_ids)
    n_covered = len(covered_ids)
    n_total = len(specs)
    pct = (n_covered / n_total * 100) if n_total > 0 else 0

    # Output
    print("=== Behavioral Traceability ===")
    print(f"BEHAVIOR.md: {n_total} behavioral statements parsed")
    for fr in file_reports:
        print(fr)
    print()

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  {e}")
        print()

    print(f"COVERAGE: {n_covered}/{n_total} behavioral statements covered ({pct:.0f}%)")

    if uncovered_ids:
        print(f"\nUNCOVERED (remaining {len(uncovered_ids)}):")
        for bid in uncovered_ids:
            desc = specs[bid]
            # Truncate long descriptions
            if len(desc) > 72:
                desc = desc[:69] + "..."
            print(f"  {bid}: {desc}")

    print()
    if errors:
        print(f"RESULT: {len(errors)} error(s) found -- FAIL")
        return 1
    else:
        print("RESULT: 0 errors -- OK")
        return 0


# ---------------------------------------------------------------------------
# Changed-file mode
# ---------------------------------------------------------------------------

def run_changed_file(filepath: str) -> int:
    """
    Report which behavioral statements are affected by an edit to a .sty file.
    Parses the file for @behavior tags and reports which spec IDs are touched.
    Returns 0 always (informational only).
    """
    if not filepath.endswith(".sty"):
        return 0

    if not os.path.isfile(filepath):
        return 0

    macros, bc, ic, uc = parse_sty_file(filepath)

    if bc == 0 and ic == 0:
        # No traceability tags in this file -- nothing to report
        return 0

    # Collect all behavior IDs referenced
    affected_ids: Set[str] = set()
    for mi in macros:
        affected_ids.update(mi.behavior_ids)

    # Also resolve @implements chains
    name_to_macro: Dict[str, MacroInfo] = {}
    for mi in macros:
        name_to_macro[mi.name] = mi

    for mi in macros:
        for impl_ref in mi.implements:
            target = name_to_macro.get(impl_ref)
            if target:
                affected_ids.update(target.behavior_ids)

    if affected_ids:
        specs = parse_behavior_md(BEHAVIOR_MD)
        id_list = sorted(affected_ids)
        descriptions = []
        for bid in id_list:
            desc = specs.get(bid, "(unknown)")
            if len(desc) > 50:
                desc = desc[:47] + "..."
            descriptions.append(f"{bid}")
        print(f"Edit touches code implementing: {', '.join(descriptions)}")
        print("  -- verify BEHAVIOR.md still matches.")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = sys.argv[1:]

    if "--changed-file" in args:
        idx = args.index("--changed-file")
        if idx + 1 < len(args):
            filepath = args[idx + 1]
            return run_changed_file(filepath)
        else:
            print("ERROR: --changed-file requires a file path", file=sys.stderr)
            return 1

    return run_full_check()


if __name__ == "__main__":
    sys.exit(main())
