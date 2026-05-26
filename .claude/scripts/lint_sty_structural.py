#!/usr/bin/env python3
"""
lint_sty_structural.py — Structural TeX linter for .sty files.

Parses .sty files with brace-depth tracking to enforce code conventions
defined in docs/CONVENTIONS.md.  Uses brace-depth tracking (not a full TeX
parser) to identify macro body boundaries.

Checks:
  1. Missing % at end of line inside macro bodies
  2. If/fi nesting depth exceeding 3 inside any macro body
  3. Macro body length exceeding 30 lines
  4. Bare \\codep@tmp (no semantic suffix)
  5. \\errmessage / \\message  (must use \\PackageError etc.)
  6. \\usepackage in .sty  (must use \\RequirePackage)
  7. \\everypar  (must use \\AddToHook{para/begin})
  8. Raw destination primitives outside \\codep@emit@destination

Exit code: 0 if no errors (warnings OK), 1 if any errors.

Usage:
  python3 lint_sty_structural.py file.sty ...
  python3 lint_sty_structural.py          # defaults to codependent.sty + codependent-render.sty
"""

import re
import sys
import os
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

class Issue:
    def __init__(self, filename: str, line_start: int,
                 line_end: Optional[int], level: str, message: str):
        self.filename = filename
        self.line_start = line_start
        self.line_end = line_end
        self.level = level
        self.message = message

    def format(self) -> str:
        if self.line_end is not None and self.line_end != self.line_start:
            loc = f"{self.line_start}-{self.line_end}"
        else:
            loc = str(self.line_start)
        return f"{self.filename}:{loc}: {self.level}: {self.message}"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def strip_comments(line: str) -> str:
    """Return the code portion of a line (before any unescaped %).
    Handles \\% (escaped percent — not a comment)."""
    result = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and i + 1 < len(line):
            result.append(ch)
            result.append(line[i + 1])
            i += 2
        elif ch == '%':
            break
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


def is_comment_line(line: str) -> bool:
    """True if the line (after stripping leading whitespace) starts with %."""
    return line.lstrip().startswith('%')


def is_blank_line(line: str) -> bool:
    return line.strip() == ''


def line_number_for_offset(content: str, offset: int) -> int:
    """Return a 1-indexed line number for a character offset."""
    return content.count('\n', 0, offset) + 1


def is_commented_offset(content: str, offset: int) -> bool:
    """True if offset is preceded by an unescaped % on the same line."""
    line_start = content.rfind('\n', 0, offset) + 1
    prefix = content[line_start:offset]
    stripped = re.sub(r'\\%', '', prefix)
    return '%' in stripped


def in_any_range(offset: int, ranges: List[Tuple[int, int]]) -> bool:
    return any(start <= offset <= end for start, end in ranges)


# ---------------------------------------------------------------------------
# Line-end check (inside macro bodies)
# ---------------------------------------------------------------------------

# Tokens that, when a line ends with them (code portion), do NOT need %.
# These are TeX conditional keywords that are harmless without % in practice,
# and standalone control sequences that produce no typeset output.
# We check the STRIPPED code (after strip_comments removes trailing whitespace).
_SAFE_LINE_ENDINGS_RE = re.compile(
    r'\\(?:'
    # Conditional branch markers (don't produce output)
    r'else|fi|or'
    # TeX primitives that are safe alone
    r'|endcsname|begingroup|endgroup'
    r')$'
)


def line_end_needs_percent(raw_line: str, code: str) -> bool:
    """Return True if this line needs (and is missing) a trailing %.

    A line does NOT need % if it:
    - is blank
    - is a comment line (starts with %)
    - ends with %, {, }, \\\\, or \\relax (in the raw line before newline)
    - its code portion is empty after stripping
    - is a \\begin{...} or \\end{...} line
    - ends with a safe standalone control word (\\else, \\fi, \\or, etc.)
    """
    if is_blank_line(raw_line):
        return False
    if is_comment_line(raw_line):
        return False

    code_stripped = code.rstrip()
    if not code_stripped:
        return False

    raw_stripped = raw_line.rstrip('\n\r').rstrip()
    if not raw_stripped:
        return False

    if raw_stripped.endswith('%'):
        return False
    if raw_stripped.endswith('{'):
        return False
    if raw_stripped.endswith('}'):
        return False
    if raw_stripped.endswith('\\\\'):
        return False
    if raw_stripped.endswith('\\relax'):
        return False

    # \\begin{...} or \\end{...}
    if re.match(r'\s*\\(?:begin|end)\s*\{', raw_line):
        return False

    # Safe standalone control words (\\else, \\fi, \\or, \\endcsname, etc.)
    if _SAFE_LINE_ENDINGS_RE.search(code_stripped):
        return False

    return True


# ---------------------------------------------------------------------------
# if/fi depth tracking
# ---------------------------------------------------------------------------

IF_OPEN_RE = re.compile(
    r'\\if(?:x|num|bool|case|dim|hmode|vmode|mmode|inner|void|eof|'
    r'true|false|cat|token|undefined|csname|[a-zA-Z@]*)'
)
FI_RE = re.compile(r'\\fi(?=[^a-zA-Z@]|$)')


def count_if_delta(code: str) -> int:
    opens = len(IF_OPEN_RE.findall(code))
    closes = len(FI_RE.findall(code))
    return opens - closes


# ---------------------------------------------------------------------------
# Whole-file checks (independent of macro bodies)
# ---------------------------------------------------------------------------

def check_whole_file(basename: str, lineno: int, code: str) -> List[Issue]:
    """Checks that apply everywhere: checks 4-7."""
    issues: List[Issue] = []

    # Check 4: bare \codep@tmp (not followed by @ or a letter/digit)
    for m in re.finditer(r'\\codep@tmp(?=[^@a-zA-Z]|$)', code):
        issues.append(Issue(basename, lineno, None, "ERROR",
            "bare \\codep@tmp (use semantic suffix, e.g. \\codep@tmp@name)"))

    # Check 5: \errmessage
    if re.search(r'\\errmessage\b', code):
        issues.append(Issue(basename, lineno, None, "ERROR",
            "\\errmessage found — use \\PackageError{codependent}{...}{...}"))

    # Check 5: \message (not preceded by "Package")
    for m in re.finditer(r'\\message\b', code):
        start = m.start()
        prefix = code[max(0, start - 7):start]
        if not prefix.endswith('Package'):
            issues.append(Issue(basename, lineno, None, "ERROR",
                "\\message found — use \\PackageInfo{codependent}{...}"))
            break

    # Check 6: \usepackage
    if re.search(r'\\usepackage\b', code):
        issues.append(Issue(basename, lineno, None, "ERROR",
            "\\usepackage in .sty — use \\RequirePackage instead"))

    # Check 7: \everypar
    if re.search(r'\\everypar\b', code):
        issues.append(Issue(basename, lineno, None, "ERROR",
            "\\everypar found — use \\AddToHook{para/begin}{...}"))

    return issues


# ---------------------------------------------------------------------------
# Destination primitive centralization (LD1)
# ---------------------------------------------------------------------------

_DESTINATION_PRIMITIVES = (
    r'Hy@raisedlink',
    r'hyper@anchorstart',
    r'hyper@anchorend',
    r'hypertarget',
    r'hyperdef',
    r'pdfdest',
    r'pdfobj',
)
_DESTINATION_PRIMITIVE_NAMES_RE = r'(?:' + '|'.join(
    _DESTINATION_PRIMITIVES) + r')'
_DESTINATION_PRIMITIVE_RE = re.compile(
    r'(?:'
    r'\\' + _DESTINATION_PRIMITIVE_NAMES_RE + r'(?=[^a-zA-Z@]|$)'
    r'|'
    r'\\csname\s+' + _DESTINATION_PRIMITIVE_NAMES_RE + r'\s*\\endcsname'
    r')'
)

_DESTINATION_HELPER_DEF_RE = re.compile(
    r'\\(?:def|newcommand\*?|providecommand\*?|DeclareRobustCommand\*?)'
    r'\s*\{?\\codep@emit@destination\}?'
)


def _extract_brace_span(content: str, start: int) -> Optional[Tuple[int, int]]:
    """Return the inclusive span of a balanced {...} group."""
    if start < 0 or start >= len(content) or content[start] != '{':
        return None
    depth = 1
    i = start + 1
    while i < len(content) and depth > 0:
        c = content[i]
        if c == '\\' and i + 1 < len(content):
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return (start, i)
        i += 1
    return None


def _first_unescaped_open_brace(content: str, start: int) -> Optional[int]:
    i = start
    while i < len(content):
        c = content[i]
        if c == '\\' and i + 1 < len(content):
            i += 2
            continue
        if c == '{':
            return i
        if c == '\n':
            # TeX definitions in this codebase keep the body opener on the
            # definition line; do not accidentally swallow later definitions.
            return None
        i += 1
    return None


def destination_helper_body_ranges(content: str) -> List[Tuple[int, int]]:
    """Find bodies of \\codep@emit@destination definitions by exact name."""
    ranges: List[Tuple[int, int]] = []
    for match in _DESTINATION_HELPER_DEF_RE.finditer(content):
        if is_commented_offset(content, match.start()):
            continue
        open_brace = _first_unescaped_open_brace(content, match.end())
        if open_brace is None:
            continue
        body_span = _extract_brace_span(content, open_brace)
        if body_span is not None:
            ranges.append(body_span)
    return ranges


def check_destination_primitives(basename: str, content: str) -> List[Issue]:
    """Forbid raw destination primitives outside the canonical helper body."""
    helper_ranges = destination_helper_body_ranges(content)
    issues: List[Issue] = []
    for match in _DESTINATION_PRIMITIVE_RE.finditer(content):
        if is_commented_offset(content, match.start()):
            continue
        if in_any_range(match.start(), helper_ranges):
            continue
        primitive = match.group(0)
        issues.append(Issue(
            basename,
            line_number_for_offset(content, match.start()),
            None,
            "ERROR",
            f"raw destination primitive {primitive} outside "
            "\\codep@emit@destination body"))
    return issues


# ---------------------------------------------------------------------------
# Macro definition detection helpers
# ---------------------------------------------------------------------------

# Matches a macro def keyword and captures which kind it is.
# Group 1: \def family (edef/gdef/xdef/long def) — 0 groups to skip
# Group 2: \newcommand/\renewcommand/\providecommand — 1 group to skip  ({\name})
# Group 3: \NewDocumentCommand etc. — 2 groups to skip ({\name}{spec})
_DEF_RE = re.compile(
    r'\\('
    r'(?:long\s*)?(?:[egx]def|def)'           # group 1: \def family
    r')(?=[^a-zA-Z@]|$)'
    r'|\\('
    r'(?:new|renew|provide)command\*?'         # group 2: \newcommand family
    r')(?=[^a-zA-Z@]|$)'
    r'|\\('
    r'(?:New|Renew|Provide|Declare)DocumentCommand'  # group 3: xparse family
    r')(?=[^a-zA-Z@]|$)'
)

# Extract the macro name after the keyword.
# Handles \def\name, \newcommand{\name}, \newcommand*{\name}, \newcommand\name.
_DEF_NAME_RE = re.compile(
    r'\\(?:'
    r'(?:long\s*)?(?:[egx]def|def)'
    r'|(?:new|renew|provide)command\*?'
    r'|(?:New|Renew|Provide|Declare)DocumentCommand'
    r')\s*(?:'
    r'\{\\([a-zA-Z@*]+)\}'    # {\name} — group 1
    r'|\{\\([a-zA-Z@*]+)'     # {\name  (unclosed, name at depth 1) — group 2
    r'|\\([a-zA-Z@*]+)'       # \name — group 3
    r')'
)


def _detect_macro_def(code: str) -> Optional[Tuple[str, int]]:
    """If `code` starts a macro definition at depth 0, return (name, groups_to_skip).
    groups_to_skip: 0 for \\def, 1 for \\newcommand{\\name}, 2 for \\NewDocumentCommand.

    Returns None if no macro def found.

    Only detects the FIRST macro def on the line.
    """
    m = _DEF_RE.search(code)
    if m is None:
        return None

    if m.group(1):
        # \def family — name is the next control sequence, no brace groups to skip
        groups = 0
    elif m.group(2):
        # \newcommand family — name is in {\name}, 1 group to skip
        groups = 1
    else:
        # \NewDocumentCommand etc. — 2 groups to skip: {\name}{argspec}
        groups = 2

    name_m = _DEF_NAME_RE.search(code)
    if name_m is None:
        return None
    name = name_m.group(1) or name_m.group(2) or name_m.group(3)
    if not name:
        return None

    return (name, groups)


# ---------------------------------------------------------------------------
# Brace scanner: yields events from the code portion of a line.
# ---------------------------------------------------------------------------

def scan_depth_events(code: str, start_depth: int):
    """Yield (depth_before, brace_char, depth_after) for each unescaped brace."""
    d = start_depth
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == '\\' and i + 1 < len(code):
            i += 2
            continue
        if ch == '{':
            before = d
            d += 1
            yield before, '{', d
        elif ch == '}':
            before = d
            d -= 1
            yield before, '}', d
        i += 1


# ---------------------------------------------------------------------------
# The line-wise linter
#
# Algorithm:
#   For each non-comment line:
#     1. If not in_body and global depth == 0:
#        check if this line starts a macro definition.
#        If so, set pending_name and pending_skip.
#     2. Scan brace events:
#        - When we see '{' at d_before == 0 (i.e. d_before == pending_def_depth):
#          * If pending_skip > 0: decrement pending_skip (skip this brace group)
#          * If pending_skip == 0 and pending_name: open macro body
#        - When we see '}' that closes below body_depth: close macro body
#     3. Line-level checks (only when in_body for check 1):
#        - Check 1: missing %
#        - Check 2: if/fi depth
#        - Check 3: line count (checked at body close)
#     4. Checks 4-7: always (on code portion)
#
# Key invariants:
#   - pending_name is only set when depth == 0 and not in_body
#   - pending_def_depth is always 0 (we only track top-level defs)
#   - body_depth is always 1 (= pending_def_depth + 1)
#   - Inner \\def inside a macro body are NOT tracked
# ---------------------------------------------------------------------------

def _lint_file_linewise(basename: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []

    # Global brace depth (only counts at top level; inside a body this
    # stays >= body_depth until the body closes)
    depth = 0

    # Pending macro detection state
    pending_name: Optional[str] = None
    pending_skip: int = 0          # number of brace groups to skip before body

    # Current macro body state
    in_body = False
    body_name = ""
    body_start_line = 0
    body_depth = 0       # the depth level that is "inside" the body
    body_line_count = 0
    body_if_depth = 0
    body_max_if_depth = 0
    body_max_if_line = 0

    for lineno, raw_line in enumerate(lines, 1):

        # Skip pure comment lines entirely
        if is_comment_line(raw_line):
            continue

        code = strip_comments(raw_line)

        # ------------------------------------------------------------------
        # Step 4: Whole-file checks (always)
        # ------------------------------------------------------------------
        issues.extend(check_whole_file(basename, lineno, code))

        # ------------------------------------------------------------------
        # Step 1: Detect new macro def (BEFORE brace scan)
        # Only at top level (depth == 0) and when not already in a body.
        # ------------------------------------------------------------------
        depth_before_line = depth
        if not in_body and depth == 0 and pending_name is None:
            result = _detect_macro_def(code)
            if result is not None:
                pending_name, pending_skip = result

        # ------------------------------------------------------------------
        # Step 2: Brace scan + macro body open/close detection
        # ------------------------------------------------------------------
        body_opened_on_this_line = False
        body_closed_on_this_line = False

        for d_before, brace, d_after in scan_depth_events(code, depth):
            depth = d_after

            if brace == '{':
                if (pending_name is not None and
                        not in_body and
                        d_before == 0):          # pending_def_depth is always 0
                    if pending_skip > 0:
                        # This { opens a to-be-skipped group (name or argspec).
                        # We just let depth increment; when it falls back to 0
                        # we'll be ready for the next {.
                        pending_skip -= 1
                    else:
                        # This { opens the macro body.
                        in_body = True
                        body_name = pending_name
                        body_start_line = lineno
                        body_depth = d_after   # = 1
                        body_line_count = 0
                        body_if_depth = 0
                        body_max_if_depth = 0
                        body_max_if_line = lineno
                        pending_name = None
                        pending_skip = 0
                        body_opened_on_this_line = True

            elif brace == '}':
                if in_body and d_after < body_depth:
                    # Macro body just closed
                    if body_line_count > 30:
                        issues.append(Issue(basename, body_start_line, lineno, "WARN",
                            f"\\{body_name} is {body_line_count} lines (max 30)"))
                    if body_max_if_depth > 3:
                        issues.append(Issue(basename, body_max_if_line, None, "WARN",
                            f"\\{body_name}: if/fi nesting depth {body_max_if_depth} (max 3)"))
                    in_body = False
                    body_closed_on_this_line = True

        # ------------------------------------------------------------------
        # After the brace scan: if pending_name is still set but the depth
        # went above 0 (because we encountered a skip-group { without a
        # matching } on the same line), that's OK — we'll continue on the
        # next line.  But if depth went BACK to 0 due to a balanced group
        # on this line, pending_skip should be correctly decremented.
        #
        # Edge case: if pending_name was consumed (body opened), great.
        # If not, keep pending_name alive for the next line.
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # Step 3: Line-level checks inside macro body
        # ------------------------------------------------------------------
        if in_body:
            # Count this line if the body was NOT just opened here.
            if not body_opened_on_this_line:
                body_line_count += 1

                # Check 2: if/fi nesting
                if_delta = count_if_delta(code)
                body_if_depth += if_delta
                if body_if_depth > body_max_if_depth:
                    body_max_if_depth = body_if_depth
                    body_max_if_line = lineno

                # Check 1: missing %
                if line_end_needs_percent(raw_line, code):
                    issues.append(Issue(basename, lineno, None, "ERROR",
                        f"missing % at end of line inside \\{body_name}"))

    return issues


# ---------------------------------------------------------------------------
# Public entry point for a single file
# ---------------------------------------------------------------------------

def lint_file(filename: str) -> List[Issue]:
    basename = os.path.basename(filename)

    try:
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except FileNotFoundError:
        return [Issue(basename, 0, None, "ERROR", f"file not found: {filename}")]

    lines = content.splitlines(keepends=True)
    issues = _lint_file_linewise(basename, lines)
    issues.extend(check_destination_primitives(basename, content))
    return issues


# ---------------------------------------------------------------------------
# Cross-file check: enddocument hook inventory (v12 A6 / v11 R29)
# ---------------------------------------------------------------------------

# Match \AddToHook{enddocument}{ or \AtEndDocument{ on one line.
_ENDDOC_HOOK_RE = re.compile(
    r'\\(?:AddToHook\s*\{\s*enddocument\s*\}|AtEndDocument)\s*\{'
)


def _extract_brace_body(content: str, start: int) -> Optional[str]:
    """Return the substring inside {...} starting at the opening brace position.

    Returns None if braces are unbalanced (shouldn't happen on valid input).
    """
    assert content[start] == '{'
    depth = 1
    i = start + 1
    while i < len(content) and depth > 0:
        c = content[i]
        if c == '\\' and i + 1 < len(content):
            # skip next char (escaped); handles \{ \} \\ inside body
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return content[start + 1:i]
        i += 1
    return None


def check_enddoc_hook_inventory(filenames: List[str]) -> List[Issue]:
    """Enforce v12 A6 / v11 R29: exactly one enddocument hook registration
    across codependent.sty + codependent-render.sty combined; its body must
    invoke \\codep@enddoc@orchestrator."""
    registrations: List[Tuple[str, int, str]] = []  # (basename, lineno, body)

    for fn in filenames:
        basename = os.path.basename(fn)
        try:
            with open(fn, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except FileNotFoundError:
            continue

        # Build a line-offset index for lineno reporting.
        line_starts = [0]
        for i, c in enumerate(content):
            if c == '\n':
                line_starts.append(i + 1)

        for m in _ENDDOC_HOOK_RE.finditer(content):
            # Skip if this occurrence is inside a comment.  Find the start of
            # its line; if an unescaped % precedes the match on the same line,
            # treat as comment.
            line_start = content.rfind('\n', 0, m.start()) + 1
            pre = content[line_start:m.start()]
            # Strip escaped % before checking for comment marker.
            stripped = re.sub(r'\\%', '', pre)
            if '%' in stripped:
                continue

            open_brace = m.end() - 1  # position of the { captured in the regex
            body = _extract_brace_body(content, open_brace)
            if body is None:
                body = "<unbalanced-braces>"
            # 1-indexed line number of the match.
            lineno = 1
            for idx, ls in enumerate(line_starts):
                if ls > m.start():
                    lineno = idx  # previous was last <= m.start()
                    break
            else:
                lineno = len(line_starts)
            registrations.append((basename, lineno, body))

    issues: List[Issue] = []
    if len(registrations) == 0:
        issues.append(Issue(
            "<cross-file>", 0, None, "ERROR",
            "enddocument hook inventory: 0 registrations found; "
            "expected exactly 1 (\\AddToHook{enddocument}{...} invoking "
            "\\codep@enddoc@orchestrator)"))
    elif len(registrations) > 1:
        sites = ", ".join(f"{b}:{ln}" for b, ln, _ in registrations)
        issues.append(Issue(
            "<cross-file>", 0, None, "ERROR",
            f"enddocument hook inventory: {len(registrations)} registrations "
            f"found ({sites}); expected exactly 1"))
    else:
        basename, lineno, body = registrations[0]
        if "\\codep@enddoc@orchestrator" not in body:
            issues.append(Issue(
                basename, lineno, None, "ERROR",
                "enddocument hook body does not invoke "
                "\\codep@enddoc@orchestrator; per v12 A6 the single "
                "enddocument registration must delegate to the orchestrator"))
    return issues





# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def should_check_enddoc_inventory(filenames: List[str]) -> bool:
    basenames = {os.path.basename(fn) for fn in filenames}
    return {"codependent.sty", "codependent-render.sty"}.issubset(basenames)


def main() -> int:
    if len(sys.argv) > 1:
        filenames = sys.argv[1:]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        filenames = [
            os.path.join(project_root, "codependent.sty"),
            os.path.join(project_root, "codependent-render.sty"),
        ]

    all_issues: List[Issue] = []
    for fn in filenames:
        all_issues.extend(lint_file(fn))

    # Cross-file check: enddocument hook inventory (v12 A6).
    if should_check_enddoc_inventory(filenames):
        all_issues.extend(check_enddoc_hook_inventory(filenames))

    all_issues.sort(key=lambda iss: (iss.filename, iss.line_start))

    has_errors = False
    for issue in all_issues:
        print(issue.format())
        if issue.level == "ERROR":
            has_errors = True

    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
