#!/usr/bin/env python3
"""CORE install-discipline linter.

This script intentionally implements the W05-INSTALL-DISCIPLINE-CORE two-tier
contract:

* ERROR diagnostics are hard failures in the standalone source lint.
* WARN diagnostics are visible but non-fatal reminders for CONTRACT-owned
  survivors. CONTRACT can promote those by flipping
  DEFERRED_INSTALL_DIAGNOSTICS_ARE_ERRORS below.

The script also owns small synthetic fixture self-tests under
.claude/scripts/lint-fixtures/.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = PROJECT_ROOT / "codependent.sty"
FIXTURE_ROOT = PROJECT_ROOT / ".claude" / "scripts" / "lint-fixtures"
INSTALL_FIXTURE_DIR = FIXTURE_ROOT / "install-discipline"
TRACK2_FIXTURE_DIR = FIXTURE_ROOT / "track2-exception"
CORE_BASELINE_DIR = PROJECT_ROOT / "testfiles" / "baselines" / "W05-INSTALL-DISCIPLINE-CORE"

# CONTRACT flips this single module-level switch. CORE leaves it False so
# deferred survivor diagnostics are WARN-only.
DEFERRED_INSTALL_DIAGNOSTICS_ARE_ERRORS = False

INSTALL_KINDS = [
    "pretocmd",
    "apptocmd",
    "AddToHook",
    "backend-hook",
    "macro-append",
    "theorem-name-link-wrap",
    "lifecycle-rewrap",
    "command-wrap",
    "dynamic-command-wrap",
    "counter-alias",
]

RAW_INSTALL_PRIMITIVES = [
    "pretocmd",
    "apptocmd",
    "AddToHook",
    "AtBeginEnvironment",
    "AtEndEnvironment",
    "AfterEndEnvironment",
    "BeforeBeginEnvironment",
    "appto",
    "gappto",
    "preto",
    "gpreto",
]

RAW_PRIMITIVE_RE = re.compile(
    r"\\(?:" + "|".join(re.escape(p) for p in RAW_INSTALL_PRIMITIVES) + r")(?=[^A-Za-z@]|$)"
)
INSTALL_KIND_ALLOW_RE = re.compile(
    r"\\codep@install@kind@allow\{([^{}]+)\}\{([^{}]+)\}"
)
ALLOW_ANNOTATION = "lint-install-discipline: allow raw-install"
SUBSTRATE_BEGIN_MARKERS = (
    "W05-INSTALL-DISCIPLINE-CORE P01: typed installer substrate",
    "LINT-INSTALL-DISCIPLINE: BEGIN typed-installer-substrate",
)
SUBSTRATE_END_MARKERS = (
    "\\codep@envtrack@config@write",
    "LINT-INSTALL-DISCIPLINE: END typed-installer-substrate",
)

PENDING_ERROR_OWNERS = {
    "track2-effect-annotation": "P03",
    "missing-proof-env-lifecycle-migration": "P05",
    "missing-track1-equation-lifecycle-migration": "P05",
    "missing-track2-carrier-migration": "P05",
    "missing-footnote-command-wrap-migration": "P05",
    "missing-addcontentsline-command-wrap-migration": "P05",
    "missing-newlist-command-wrap-migration": "P05",
    "missing-newlabel-command-wrap-migration": "P05",
    "missing-ref-family-command-wrap-migration": "P05",
    "missing-label-command-wrap-migration": "P05",
    "missing-proof-heading-carrier-migration": "P05",
    "missing-suppresscmd-migration": "P05",
    "missing-amsthm-shim-migration": "P05",
}

KERNEL_RESET_LIST_EXCEPTION = {
    "name": "kernel-reset-list-rewrite",
    "file": "codependent.sty",
    "line_start": 995,
    "line_end": 996,
    "macro": "codep@removefromreset",
    "target_compact": r"\g@addto@macro\csnamecl@#2\endcsname",
}


@dataclass(frozen=True)
class Diagnostic:
    tier: str
    path: Path
    line: int
    code: str
    message: str

    def format(self) -> str:
        rel = _relpath(self.path)
        return f"{self.tier}: {rel}:{self.line}: {self.code}: {self.message}"


def _relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _strip_comments(line: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            result.extend([ch, line[i + 1]])
            i += 2
        elif ch == "%":
            break
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())
    return starts


def _line_for_offset(starts: Sequence[int], offset: int) -> int:
    # Small files only; simple scan keeps dependencies out of the linter.
    line = 1
    for idx, start in enumerate(starts, start=1):
        if start > offset:
            break
        line = idx
    return line


def _tex_parse_diagnostics(path: Path, text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    depth = 0
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        code = _strip_comments(raw_line)
        i = 0
        while i < len(code):
            ch = code[i]
            if ch == "\\" and i + 1 < len(code):
                i += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    diagnostics.append(
                        Diagnostic(
                            "ERROR",
                            path,
                            lineno,
                            "parse-error",
                            "unbalanced TeX braces: closing brace without opener",
                        )
                    )
                    depth = 0
            i += 1
    if depth != 0:
        diagnostics.append(
            Diagnostic(
                "ERROR",
                path,
                max(1, len(text.splitlines())),
                "parse-error",
                f"unbalanced TeX braces: {depth} unclosed group(s)",
            )
        )
    return diagnostics


def _python_parse_diagnostics(path: Path, text: str) -> list[Diagnostic]:
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [
            Diagnostic(
                "ERROR",
                path,
                exc.lineno or 1,
                "parse-error",
                exc.msg,
            )
        ]
    return []


def _parse_diagnostics(path: Path, text: str) -> list[Diagnostic]:
    if path.suffix == ".py":
        return _python_parse_diagnostics(path, text)
    return _tex_parse_diagnostics(path, text)


def _substrate_ranges(lines: Sequence[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for idx, line in enumerate(lines, start=1):
        if start is None and any(marker in line for marker in SUBSTRATE_BEGIN_MARKERS):
            start = idx
            continue
        if start is not None and any(marker in line for marker in SUBSTRATE_END_MARKERS):
            ranges.append((start, idx))
            start = None
    if start is not None:
        ranges.append((start, len(lines)))
    return ranges


def _line_in_ranges(line: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _has_line_allow_annotation(lines: Sequence[str], zero_idx: int) -> bool:
    candidates = [zero_idx]
    if zero_idx > 0:
        candidates.append(zero_idx - 1)
    return any(ALLOW_ANNOTATION in lines[idx] for idx in candidates)


def _compact_contract_code(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _line_in_named_macro(text: str, macro_name: str, line: int) -> bool:
    span = _macro_line_span(text, macro_name)
    if span is None:
        return False
    start, end, _body = span
    return start <= line <= end


def _has_exact_kernel_reset_list_append(code_window: str) -> bool:
    compact = _compact_contract_code(code_window)
    return KERNEL_RESET_LIST_EXCEPTION["target_compact"] in compact


def _is_kernel_reset_list_exception(
    path: Path,
    text: str,
    line: int,
    code_window: str,
) -> bool:
    if not _has_exact_kernel_reset_list_append(code_window):
        return False
    if not _line_in_named_macro(text, KERNEL_RESET_LIST_EXCEPTION["macro"], line):
        return False
    if path.resolve() == SOURCE_PATH.resolve():
        return (
            line == KERNEL_RESET_LIST_EXCEPTION["line_start"]
            and path.name == KERNEL_RESET_LIST_EXCEPTION["file"]
        )
    # Synthetic positive fixture mirrors the exact macro/target shape without
    # padding hundreds of blank lines just to reproduce source line 995.
    return path.name == "pass-named-exception-kernel-reset-list.sty"


def _has_raw_activation_let(code: str) -> bool:
    direct = re.search(
        r"\\let\\codep@[A-Za-z@]+\\codep@[A-Za-z@]+@active\b",
        code,
    )
    csname = re.search(
        r"\\let\\csname\s*codep@[A-Za-z@]+@active\\endcsname\s*\\codep@[A-Za-z@]+\b",
        code,
    )
    return bool(direct or csname)


def _scan_raw_install_primitives(path: Path, text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    lines = text.splitlines()
    substrate = _substrate_ranges(lines)
    for zero_idx, raw_line in enumerate(lines):
        line = zero_idx + 1
        if _line_in_ranges(line, substrate) or _has_line_allow_annotation(lines, zero_idx):
            continue
        code = _strip_comments(raw_line)
        for match in RAW_PRIMITIVE_RE.finditer(code):
            if code[max(0, match.start() - len("\\string")) : match.start()] == "\\string":
                continue
            primitive = match.group(0)
            diagnostics.append(
                Diagnostic(
                    "WARN",
                    path,
                    line,
                    "unclassified-raw-install-primitive",
                    f"raw {primitive} outside typed installer allowlist; CORE surfaces this as WARN, CONTRACT owns hard closure",
                )
            )
    return diagnostics


def _scan_contract_survivors(path: Path, text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    lines = text.splitlines()
    substrate = _substrate_ranges(lines)
    for zero_idx, raw_line in enumerate(lines):
        line = zero_idx + 1
        if _line_in_ranges(line, substrate):
            continue
        code = _strip_comments(raw_line)
        code_window = "".join(_strip_comments(l) for l in lines[zero_idx : zero_idx + 3])

        if "\\g@addto@macro" in code:
            if "\\csname cl@" in code_window:
                if _is_kernel_reset_list_exception(path, text, line, code_window):
                    continue
                diagnostics.append(
                    Diagnostic(
                        "WARN",
                        path,
                        line,
                        "kernel-reset-list-raw-gaddto-macro",
                        "raw kernel reset-list append is CONTRACT-owned until typed handling or an exception lands",
                    )
                )
            else:
                diagnostics.append(
                    Diagnostic(
                        "WARN",
                        path,
                        line,
                        "contract-owned-gaddto-macro",
                        "raw \\g@addto@macro callsite is visible to CORE but CONTRACT owns final classification",
                    )
                )

        compact = re.sub(r"\s+", "", code)
        if "\\protected\\edef#2" in compact:
            diagnostics.append(
                Diagnostic(
                    "WARN",
                    path,
                    line,
                    "dynamic-command-wrap-protected-edef",
                    "raw \\protected\\edef#2 dynamic command wrapper is deferred to CONTRACT",
                )
            )

        if re.search(r"\\let\\csname\s*c@", code):
            diagnostics.append(
                Diagnostic(
                    "WARN",
                    path,
                    line,
                    "counter-alias-raw-let",
                    "raw counter-alias \\let\\csname c@... is deferred to CONTRACT",
                )
            )

        if _has_raw_activation_let(code):
            diagnostics.append(
                Diagnostic(
                    "WARN",
                    path,
                    line,
                    "activation-let-raw",
                    "raw activation \\let to @active callback is deferred to CONTRACT classification",
                )
            )
    return diagnostics


def _check_install_kind_enum(path: Path, text: str, *, required: bool) -> list[Diagnostic]:
    uncommented = "\n".join(_strip_comments(line) for line in text.splitlines())
    matches = list(INSTALL_KIND_ALLOW_RE.finditer(uncommented))
    if not matches:
        if required:
            return [
                Diagnostic(
                    "ERROR",
                    path,
                    1,
                    "install-kind-enum-mismatch",
                    "missing \\codep@install@kind@allow registration block; expected exactly the 10 install-kinds",
                )
            ]
        return []

    kinds = [m.group(1) for m in matches]
    if kinds == INSTALL_KINDS:
        return []

    starts = _line_starts(text)
    first_line = _line_for_offset(_line_starts(uncommented), matches[0].start())
    missing = [kind for kind in INSTALL_KINDS if kind not in kinds]
    extra = [kind for kind in kinds if kind not in INSTALL_KINDS]
    duplicate = sorted({kind for kind in kinds if kinds.count(kind) > 1})
    parts = [f"saw {kinds!r}; expected {INSTALL_KINDS!r}"]
    if missing:
        parts.append(f"missing={missing!r}")
    if extra:
        parts.append(f"extra={extra!r}")
    if duplicate:
        parts.append(f"duplicate={duplicate!r}")
    return [
        Diagnostic(
            "ERROR",
            path,
            first_line,
            "install-kind-enum-mismatch",
            "; ".join(parts),
        )
    ]


def _macro_line_span(text: str, macro_name: str) -> tuple[int, int, str] | None:
    escaped = re.escape("\\" + macro_name)
    define_re = re.compile(
        r"\\(?:long\\)?def\s*" + escaped + r"(?![A-Za-z@])|"
        r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{"
        + escaped
        + r"\}"
    )
    lines = text.splitlines()
    for start_idx, line in enumerate(lines):
        if not define_re.search(_strip_comments(line)):
            continue
        depth = 0
        seen_open = False
        collected: list[str] = []
        for end_idx in range(start_idx, len(lines)):
            raw_line = lines[end_idx]
            collected.append(raw_line)
            code = _strip_comments(raw_line)
            i = 0
            while i < len(code):
                ch = code[i]
                if ch == "\\" and i + 1 < len(code):
                    i += 2
                    continue
                if ch == "{":
                    depth += 1
                    seen_open = True
                elif ch == "}":
                    depth -= 1
                i += 1
            if seen_open and depth == 0:
                return start_idx + 1, end_idx + 1, "\n".join(collected)
    return None


def _check_track2_annotation(path: Path, text: str, *, required: bool) -> list[Diagnostic]:
    if "\\codep@flusheqrange" not in text and not required:
        return []
    span = _macro_line_span(text, "codep@flusheqrange")
    if span is None:
        return [
            Diagnostic(
                "ERROR",
                path,
                1,
                "track2-effect-annotation",
                "could not locate \\codep@flusheqrange definition for Track-2 annotation check",
            )
        ]
    start, _end, body = span
    lines = text.splitlines()
    prefix_start = max(0, start - 4)
    annotation_window = "\n".join(lines[prefix_start : start - 1] + [body])
    count = annotation_window.count("%@effect track2-shipout-order-write")
    if count == 1:
        return []
    return [
        Diagnostic(
            "ERROR",
            path,
            start,
            "track2-effect-annotation",
            f"expected exactly one %@effect track2-shipout-order-write annotation on \\codep@flusheqrange; found {count}",
        )
    ]


def _compact_code(text: str) -> str:
    code = "".join(_strip_comments(line) for line in text.splitlines())
    return re.sub(r"\s+", "", code)


def _macro_compact(text: str, macro_name: str) -> tuple[int, str] | None:
    span = _macro_line_span(text, macro_name)
    if span is None:
        return None
    start, _end, body = span
    return start, _compact_code(body)


def _has(compact: str, pattern: str) -> bool:
    return pattern in compact


def _line_of_macro(text: str, macro_name: str, fallback: int = 1) -> int:
    span = _macro_line_span(text, macro_name)
    return span[0] if span else fallback


def _line_of_first(text: str, needle: str, fallback: int = 1) -> int:
    idx = text.find(needle)
    if idx < 0:
        return fallback
    return _line_for_offset(_line_starts(text), idx)


def _check_load_bearing_migrations(path: Path, text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    compact = _compact_code(text)

    def add(code: str, line: int, message: str) -> None:
        diagnostics.append(Diagnostic("ERROR", path, line, code, message))

    hookproof = _macro_compact(text, "codep@hookproof")
    if hookproof is None or not all(
        _has(hookproof[1], pat)
        for pat in (
            r"\codep@hook@install{pre-begin}{proof}",
            r"\codep@hook@install{pre-end}{proof}",
            r"\codep@hook@install{after-env}{proof}",
        )
    ):
        add(
            "missing-proof-env-lifecycle-migration",
            _line_of_macro(text, "codep@hookproof", _line_of_first(text, r"\AtBeginEnvironment{proof}")),
            "proof environment lifecycle hooks must use typed \\codep@hook@install for pre-begin/pre-end/after-env",
        )

    trackeq = _macro_compact(text, "codep@trackeqenv")
    if trackeq is None or not all(
        _has(trackeq[1], pat)
        for pat in (
            r"\codep@hook@install{post-begin}",
            r"\codep@hook@install{pre-end}",
            r"\codep@hook@install{after-env}",
        )
    ):
        add(
            "missing-track1-equation-lifecycle-migration",
            _line_of_macro(text, "codep@trackeqenv", _line_of_first(text, r"\AtBeginEnvironment{#1}")),
            "Track-1 equation lifecycle hooks must use typed \\codep@hook@install for post-begin/pre-end/after-env",
        )

    trackalign = _macro_compact(text, "codep@trackalignenv")
    if trackalign is None or not _has(
        trackalign[1],
        r"\codep@hook@install{after-env}{#1}{track2-shipout-order-write}{\codep@flusheqrange}",
    ):
        add(
            "missing-track2-carrier-migration",
            _line_of_macro(text, "codep@trackalignenv", _line_of_first(text, r"\AfterEndEnvironment{#1}{\codep@flusheqrange}")),
            "Track-2 AfterEndEnvironment carrier must use typed after-env install with track2-shipout-order-write",
        )

    command_wrap_groups = [
        (
            "missing-footnote-command-wrap-migration",
            "footnote command wrapper must use \\codep@target@install{command-wrap}{\\footnote}",
            _line_of_first(text, r"\let\codep@orig@footnote\footnote"),
            [r"\codep@target@install{command-wrap}{\footnote}"],
        ),
        (
            "missing-addcontentsline-command-wrap-migration",
            "addcontentsline wrapper must use \\codep@target@install{command-wrap}{\\addcontentsline}",
            _line_of_first(text, r"\let\codep@orig@addcontentsline\addcontentsline"),
            [r"\codep@target@install{command-wrap}{\addcontentsline}"],
        ),
        (
            "missing-newlist-command-wrap-migration",
            "enumitem newlist wrapper must use \\codep@target@install{command-wrap}{\\newlist}",
            _line_of_first(text, r"\global\let\codep@orig@newlist\newlist"),
            [r"\codep@target@install{command-wrap}{\newlist}"],
        ),
        (
            "missing-newlabel-command-wrap-migration",
            "newlabel/newlabelxx wrappers must use two typed command-wrap installs",
            _line_of_macro(text, "codep@installnewlabel", _line_of_first(text, r"\let\codep@orig@newlabel\newlabel")),
            [
                r"\codep@target@install{command-wrap}{\newlabel}",
                r"\codep@target@install{command-wrap}{\newlabelxx}",
            ],
        ),
        (
            "missing-ref-family-command-wrap-migration",
            "ref-family wrappers must use typed command-wrap installs for ref/pageref/Ref/cref/Cref/labelcref/autoref",
            _line_of_macro(text, "codep@installfrontedgerefpatch", _line_of_first(text, r"\let\codep@saved@ref\ref")),
            [
                r"\codep@target@install{command-wrap}{\ref}",
                r"\codep@target@install{command-wrap}{\pageref}",
                r"\codep@target@install{command-wrap}{\Ref}",
                r"\codep@target@install{command-wrap}{\cref}",
                r"\codep@target@install{command-wrap}{\Cref}",
                r"\codep@target@install{command-wrap}{\labelcref}",
                r"\codep@target@install{command-wrap}{\autoref}",
            ],
        ),
        (
            "missing-label-command-wrap-migration",
            "label wrapper inside begindocument/before carrier must be represented as typed command-wrap",
            _line_of_first(text, r"\let\codep@orig@label\label"),
            [r"\codep@target@install{command-wrap}{\label}"],
        ),
    ]
    for code, message, line, patterns in command_wrap_groups:
        if not all(_has(compact, pattern) for pattern in patterns):
            add(code, line, message)

    proof_heading_uses = len(re.findall(r"\\codep@proof@install@heading(?=[^A-Za-z@]|$)", _compact_code(text)))
    if proof_heading_uses < 2:
        add(
            "missing-proof-heading-carrier-migration",
            _line_of_first(text, r"\expandafter\pretocmd\csname\string\proof\endcsname"),
            "proof-heading carrier must call dedicated \\codep@proof@install@heading outside its definition",
        )

    suppresscmd = _macro_compact(text, "codep@suppresscmd")
    if suppresscmd is None or not all(
        _has(suppresscmd[1], pat)
        for pat in (
            r"\codep@target@install{pretocmd}",
            r"\codep@target@install{apptocmd}",
        )
    ):
        add(
            "missing-suppresscmd-migration",
            _line_of_macro(text, "codep@suppresscmd", _line_of_first(text, r"\pretocmd{#1}")),
            "\\codep@suppresscmd must route pretocmd/apptocmd patches through typed \\codep@target@install",
        )

    if not _has(compact, r"\codep@target@install{theorem-name-link-wrap}{\@begintheorem}"):
        add(
            "missing-amsthm-shim-migration",
            _line_of_first(text, r"\let\codep@orig@begintheorem\@begintheorem"),
            "amsthm \\@begintheorem name-link shim must use typed theorem-name-link-wrap install",
        )

    return diagnostics


def _check_no_core_baseline_dir(path: Path) -> list[Diagnostic]:
    if CORE_BASELINE_DIR.exists():
        return [
            Diagnostic(
                "ERROR",
                path,
                1,
                "unexpected-core-baseline-dir",
                f"unexpected {CORE_BASELINE_DIR.relative_to(PROJECT_ROOT)}; CORE must verify against W05-XPARSE-VMODE-FIXES instead of rotating",
            )
        ]
    return []


def _lint_source(path: Path) -> list[Diagnostic]:
    text = path.read_text(encoding="utf-8", errors="replace")
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_parse_diagnostics(path, text))
    diagnostics.extend(_check_install_kind_enum(path, text, required=True))
    diagnostics.extend(_check_track2_annotation(path, text, required=True))
    diagnostics.extend(_check_load_bearing_migrations(path, text))
    diagnostics.extend(_check_no_core_baseline_dir(path))
    diagnostics.extend(_scan_raw_install_primitives(path, text))
    diagnostics.extend(_scan_contract_survivors(path, text))
    return diagnostics


def _lint_fixture(path: Path) -> list[Diagnostic]:
    text = path.read_text(encoding="utf-8", errors="replace")
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_parse_diagnostics(path, text))

    if TRACK2_FIXTURE_DIR in path.parents:
        diagnostics.extend(_check_track2_annotation(path, text, required=True))
        return diagnostics

    diagnostics.extend(_check_install_kind_enum(path, text, required=False))
    diagnostics.extend(_scan_raw_install_primitives(path, text))
    diagnostics.extend(_scan_contract_survivors(path, text))
    return diagnostics


def _expected_path(fixture: Path) -> Path:
    return fixture.with_name(f"{fixture.stem}.expected-output.txt")


def _render_fixture_output(diagnostics: Sequence[Diagnostic]) -> str:
    if not diagnostics:
        return "PASS\n"
    return "\n".join(d.format() for d in diagnostics) + "\n"


def _fixture_files() -> list[Path]:
    roots = [INSTALL_FIXTURE_DIR, TRACK2_FIXTURE_DIR]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.glob("*.sty")))
    return files


def _run_fixture_self_tests(*, update_expected: bool) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    fixtures = _fixture_files()
    if not fixtures:
        return [
            Diagnostic(
                "ERROR",
                FIXTURE_ROOT,
                1,
                "broken-lint-fixture",
                "no install-discipline/track2 lint fixtures found",
            )
        ]

    for fixture in fixtures:
        actual = _render_fixture_output(_lint_fixture(fixture))
        expected_path = _expected_path(fixture)
        if update_expected:
            expected_path.write_text(actual, encoding="utf-8")
            continue
        if not expected_path.exists():
            diagnostics.append(
                Diagnostic(
                    "ERROR",
                    fixture,
                    1,
                    "broken-lint-fixture",
                    f"missing expected-output companion {_relpath(expected_path)}",
                )
            )
            continue
        expected = expected_path.read_text(encoding="utf-8")
        if actual != expected:
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=_relpath(expected_path),
                    tofile=f"actual:{_relpath(fixture)}",
                )
            ).rstrip()
            diagnostics.append(
                Diagnostic(
                    "ERROR",
                    fixture,
                    1,
                    "broken-lint-fixture",
                    "fixture output mismatch\n" + diff,
                )
            )
    return diagnostics


def _effective_diagnostic(diagnostic: Diagnostic, *, allow_pending_core_errors: bool) -> Diagnostic:
    if diagnostic.tier == "WARN" and DEFERRED_INSTALL_DIAGNOSTICS_ARE_ERRORS:
        return Diagnostic(
            "ERROR",
            diagnostic.path,
            diagnostic.line,
            f"deferred-promoted-{diagnostic.code}",
            diagnostic.message,
        )
    owner = PENDING_ERROR_OWNERS.get(diagnostic.code)
    if diagnostic.tier == "ERROR" and owner and allow_pending_core_errors:
        return Diagnostic(
            "WARN",
            diagnostic.path,
            diagnostic.line,
            f"pending-{owner.lower()}-{diagnostic.code}",
            diagnostic.message,
        )
    return diagnostic


def _emit(diagnostics: Iterable[Diagnostic], *, allow_pending_core_errors: bool) -> int:
    effective = [
        _effective_diagnostic(diagnostic, allow_pending_core_errors=allow_pending_core_errors)
        for diagnostic in diagnostics
    ]
    effective.sort(key=lambda d: (_relpath(d.path), d.line, d.tier, d.code, d.message))
    for diagnostic in effective:
        print(diagnostic.format())
    errors = [diagnostic for diagnostic in effective if diagnostic.tier == "ERROR"]
    if not effective:
        print("PASS: install-discipline lint found no diagnostics")
    else:
        print(
            f"SUMMARY: errors={sum(1 for d in effective if d.tier == 'ERROR')} "
            f"warnings={sum(1 for d in effective if d.tier == 'WARN')}"
        )
    return 1 if errors else 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint CORE install-discipline invariants.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional TeX/Python inputs. Defaults to codependent.sty source lint.",
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Run only synthetic lint fixture self-tests.",
    )
    parser.add_argument(
        "--no-fixtures",
        action="store_true",
        help="Skip fixture self-tests when linting source paths.",
    )
    parser.add_argument(
        "--update-fixture-expected",
        action="store_true",
        help="Developer helper: rewrite expected-output companions from current fixture output.",
    )
    parser.add_argument(
        "--allow-pending-core-errors",
        action="store_true",
        help=(
            "Bootstrap mode for P02 flake wiring only: demote P03/P05 pending "
            "source ERRORs to visible WARNs while keeping parse/enum/fixture/no-rotation "
            "errors fatal. Standalone lint does not use this."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    diagnostics: list[Diagnostic] = []

    if args.fixtures_only:
        diagnostics.extend(_run_fixture_self_tests(update_expected=args.update_fixture_expected))
        return _emit(diagnostics, allow_pending_core_errors=args.allow_pending_core_errors)

    paths = [Path(p) for p in args.paths] if args.paths else [SOURCE_PATH]
    for path in paths:
        full_path = path if path.is_absolute() else PROJECT_ROOT / path
        if not full_path.exists():
            diagnostics.append(
                Diagnostic("ERROR", full_path, 1, "parse-error", "input path does not exist")
            )
            continue
        if full_path.suffix == ".sty" and full_path.resolve() == SOURCE_PATH.resolve():
            diagnostics.extend(_lint_source(full_path))
        elif full_path.suffix == ".sty":
            diagnostics.extend(_lint_fixture(full_path))
        else:
            text = full_path.read_text(encoding="utf-8", errors="replace")
            diagnostics.extend(_parse_diagnostics(full_path, text))

    if not args.no_fixtures:
        diagnostics.extend(_run_fixture_self_tests(update_expected=args.update_fixture_expected))

    return _emit(diagnostics, allow_pending_core_errors=args.allow_pending_core_errors)


if __name__ == "__main__":
    raise SystemExit(main())
