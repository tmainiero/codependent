#!/usr/bin/env python3
"""
wrap.py - generate wrapper .tex files that inject semtex into an
existing arxiv paper source, without editing the original.

Usage:
  python wrap.py <arxiv-id>   # wrap one paper
  python wrap.py --all        # wrap every paper under papers/
  python wrap.py --list       # list wrappable papers

The generated wrapper lives at wrappers/<id>.tex and has the shape:

    % ORIGINAL PREAMBLE (verbatim, copied byte-for-byte)
    \\documentclass...
    \\usepackage...
    ...
    % SEMTEX INJECTION (added just before \\begin{document})
    \\usepackage{semtex}
    \\semtextrack{theorem,definition,proposition,lemma,
                  corollary,remark,example,proof}
    \\begin{document}
    % ORIGINAL BODY (verbatim)
    ...
    \\end{document}

The wrapper is written into a flat wrappers/ directory so the test
runner can glob wrappers/*.tex. Subfiles referenced via \\input /
\\include from the main file are SYMLINKED from papers/<id>/ into
the wrappers/ directory (or copied on platforms without symlinks)
so the wrapper compiles without chdir.

Heuristics for locating the main .tex file in an arxiv source tree
(in priority order):
  1. File literally named main.tex
  2. File containing both \\documentclass and \\begin{document}
  3. Largest .tex file by byte size that contains \\documentclass
  4. First .tex file in lexical order

This script is self-contained and runs from anywhere under
testfiles/real-world/.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PAPERS_DIR = SCRIPT_DIR / "papers"
WRAPPERS_DIR = SCRIPT_DIR / "wrappers"

SEMTEX_INJECTION = (
    "\n"
    "% ---- semtex injection (added by wrap.py) ----\n"
    "\\usepackage[conceptwarnings=off]{semtex}\n"
    "\\semtextrack{theorem,definition,proposition,lemma,"
    "corollary,remark,example,proof}\n"
    "% ---- end semtex injection ----\n"
)

# Compiled regexes for the command-rewrite pass.
# Match \newcommand or \newcommand* with brace or no-brace cmd.
RE_NEWCOMMAND = re.compile(
    r'\\newcommand\*?\s*(?:\{(\\[A-Za-z@]+)\}|(\\[A-Za-z@]+))'
)
# Match \NewDocumentCommand with brace or no-brace cmd.
RE_NEWDOCCMD = re.compile(
    r'\\NewDocumentCommand\s*(?:\{(\\[A-Za-z@]+)\}|(\\[A-Za-z@]+))'
)

RE_DOCUMENTCLASS = re.compile(r"\\documentclass\b")
RE_BEGIN_DOCUMENT = re.compile(r"\\begin\s*\{document\}")
RE_END_DOCUMENT = re.compile(r"\\end\s*\{document\}")
RE_SEMTEX_LOADED = re.compile(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{semtex\}")
RE_INPUT_INCLUDE = re.compile(
    r"\\(?:input|include|subfile)\s*\{([^}]+)\}"
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def find_main_tex(paper_dir: Path) -> Path | None:
    """Locate the main .tex file in an extracted paper directory."""
    tex_files = sorted(paper_dir.rglob("*.tex"))
    if not tex_files:
        return None

    # Rule 1: literal main.tex.
    for f in tex_files:
        if f.name == "main.tex":
            return f

    # Rule 2: contains both \documentclass and \begin{document}.
    candidates_full: list[Path] = []
    candidates_class_only: list[Path] = []
    for f in tex_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        has_class = bool(RE_DOCUMENTCLASS.search(text))
        has_begin = bool(RE_BEGIN_DOCUMENT.search(text))
        if has_class and has_begin:
            candidates_full.append(f)
        elif has_class:
            candidates_class_only.append(f)

    if candidates_full:
        # Pick the largest.
        return max(candidates_full, key=lambda p: p.stat().st_size)
    if candidates_class_only:
        return max(candidates_class_only, key=lambda p: p.stat().st_size)

    # Rule 4: first lexical.
    return tex_files[0]


def split_preamble_body(text: str) -> tuple[str, str] | None:
    """Split a tex source into (preamble_including_begin_document, body_between)."""
    m_begin = RE_BEGIN_DOCUMENT.search(text)
    if not m_begin:
        return None
    m_end = RE_END_DOCUMENT.search(text, m_begin.end())
    if not m_end:
        return None
    preamble = text[: m_begin.start()]
    body = text[m_begin.end() : m_end.start()]
    return preamble, body


def collect_dependencies(
    main_file: Path, paper_dir: Path
) -> list[Path]:
    """Collect files referenced via \\input / \\include / \\subfile from
    the main file (one level, which is enough for 95% of arxiv submissions).
    Returns paths relative to paper_dir."""
    try:
        text = main_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    deps: list[Path] = []
    for m in RE_INPUT_INCLUDE.finditer(text):
        rel = m.group(1).strip()
        # Strip optional .tex extension handling: LaTeX adds .tex if missing.
        candidate = paper_dir / rel
        if not candidate.exists():
            candidate = paper_dir / (rel + ".tex")
        if candidate.exists():
            deps.append(candidate)
    return deps


def link_or_copy(src: Path, dest: Path) -> None:
    """Symlink src -> dest, falling back to copy."""
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.symlink_to(src.resolve())
    except (OSError, NotImplementedError):
        shutil.copy2(src, dest)


def _unescaped_percent_pos(line: str) -> int:
    """Return index of first unescaped % on the line, or len(line) if none."""
    for i, ch in enumerate(line):
        if ch == "%" and (i == 0 or line[i - 1] != "\\"):
            return i
    return len(line)


def _rewrite_line_newcommand(line: str) -> tuple[str, str | None]:
    r"""Rewrite \newcommand / \newcommand* on a single line.
    Returns (new_line, description_or_None).  description is non-None only
    when a rewrite happened."""
    comment_pos = _unescaped_percent_pos(line)
    m = RE_NEWCOMMAND.search(line)
    if m is None:
        return line, None
    # Only rewrite if the match starts before any unescaped %.
    if m.start() >= comment_pos:
        return line, None
    cmd = m.group(1) or m.group(2)
    # Skip internal helpers (names containing @).
    if "@" in cmd:
        return line, None
    replacement = f"\\semtexnewcommand{{{cmd}}}"
    new_line = line[: m.start()] + replacement + line[m.end() :]
    before = m.group(0).strip()
    return new_line, f"{before} → {replacement}"


def _rewrite_line_newdoccmd(line: str) -> tuple[str, str | None]:
    r"""Rewrite \NewDocumentCommand on a single line."""
    comment_pos = _unescaped_percent_pos(line)
    m = RE_NEWDOCCMD.search(line)
    if m is None:
        return line, None
    if m.start() >= comment_pos:
        return line, None
    cmd = m.group(1) or m.group(2)
    if "@" in cmd:
        return line, None
    replacement = f"\\semtexNewDocumentCommand{{{cmd}}}"
    new_line = line[: m.start()] + replacement + line[m.end() :]
    before = m.group(0).strip()
    return new_line, f"{before} → {replacement}"


def rewrite_preamble(
    preamble: str, paper_id: str
) -> tuple[str, list[tuple[int, str]]]:
    """Walk the preamble line by line, rewriting command definitions to
    their semtex variants.  Returns (rewritten_preamble, rewrites) where
    rewrites is a list of (lineno, description) pairs (1-based)."""
    lines = preamble.splitlines(keepends=True)
    out: list[str] = []
    rewrites: list[tuple[int, str]] = []
    makeatletter_depth = 0

    for lineno, line in enumerate(lines, start=1):
        # Pass through comment-only lines.
        stripped = line.lstrip()
        if stripped.startswith("%"):
            out.append(line)
            continue

        # Update makeatletter depth (check both on this line).
        at_count = len(re.findall(r"\\makeatletter\b", line))
        end_count = len(re.findall(r"\\makeatother\b", line))
        makeatletter_depth += at_count - end_count
        # Clamp to 0 in case of malformed input.
        if makeatletter_depth < 0:
            makeatletter_depth = 0

        # Inside makeatletter block: pass through.
        if makeatletter_depth > 0:
            out.append(line)
            continue

        # Try \newcommand rewrite first.
        new_line, desc = _rewrite_line_newcommand(line)
        if desc is not None:
            out.append(new_line)
            rewrites.append((lineno, desc))
            continue

        # Try \NewDocumentCommand rewrite.
        new_line, desc = _rewrite_line_newdoccmd(line)
        if desc is not None:
            out.append(new_line)
            rewrites.append((lineno, desc))
            continue

        out.append(line)

    return "".join(out), rewrites


def wrap_paper(paper_id: str, do_rewrite: bool = True) -> bool:
    """Generate wrappers/<id>.tex for a single paper. Returns True on success."""
    paper_dir = PAPERS_DIR / paper_id
    if not paper_dir.is_dir():
        log(f"[skip] {paper_id}: papers/{paper_id}/ not found. "
            f"Run `python fetch.py {paper_id}` first.")
        return False

    main_file = find_main_tex(paper_dir)
    if main_file is None:
        log(f"[skip] {paper_id}: no .tex file found under papers/{paper_id}/")
        return False

    try:
        text = main_file.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log(f"[skip] {paper_id}: cannot read {main_file}: {e}")
        return False

    # Already uses semtex? Warn and skip.
    if RE_SEMTEX_LOADED.search(text):
        log(f"[skip] {paper_id}: already loads semtex in preamble.")
        return False

    parts = split_preamble_body(text)
    if parts is None:
        log(
            f"[skip] {paper_id}: main file {main_file.name} has no "
            f"matched \\begin{{document}} / \\end{{document}} pair."
        )
        return False
    preamble, body = parts

    if not RE_DOCUMENTCLASS.search(preamble):
        log(
            f"[skip] {paper_id}: main file {main_file.name} has no "
            f"\\documentclass in its preamble; not a wrappable main file."
        )
        return False

    # Optionally rewrite command definitions to semtex variants.
    rewrites: list[tuple[int, str]] = []
    if do_rewrite:
        preamble, rewrites = rewrite_preamble(preamble, paper_id)
        preamble_note = (
            "% Commands rewritten: \\newcommand -> \\semtexnewcommand, etc.\n"
        )
    else:
        preamble_note = (
            "% This wrapper preserves the original preamble byte-for-byte\n"
        )

    # Strip any trailing whitespace from the preamble, then inject.
    wrapper_text = (
        "% Auto-generated by wrap.py - do not edit by hand.\n"
        f"% Source paper: {paper_id}\n"
        f"% Original main file: {main_file.relative_to(paper_dir)}\n"
        "%\n"
        + preamble_note
        + "% and injects \\usepackage{semtex} just before \\begin{document}.\n"
        "%\n"
        + preamble.rstrip()
        + "\n"
        + SEMTEX_INJECTION
        + "\\begin{document}\n"
        + body
        + "\\end{document}\n"
    )

    WRAPPERS_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = WRAPPERS_DIR / f"{paper_id}.tex"
    wrapper_path.write_text(wrapper_text, encoding="utf-8")

    # Symlink any \input'd subfiles next to the wrapper so it compiles
    # without chdir into papers/<id>/.
    deps = collect_dependencies(main_file, paper_dir)
    linked = 0
    for dep in deps:
        rel = dep.relative_to(paper_dir)
        link_or_copy(dep, WRAPPERS_DIR / rel)
        linked += 1

    k = len(rewrites)
    log(
        f"[ ok ] {paper_id}: wrote {wrapper_path.name} "
        f"({len(wrapper_text)} bytes, {linked} deps linked, {k} commands rewritten)"
    )

    # Emit per-paper rewrite diff log (cap at 8 shown; first 3 + "N more").
    if rewrites:
        show = rewrites[:3] if k > 8 else rewrites[:8]
        indent = "       "
        label = "rewrites: "
        for i, (lno, desc) in enumerate(show):
            prefix = label if i == 0 else " " * len(label)
            log(f"{indent}{prefix}{desc} (line {lno})")
        if k > 8:
            hidden = k - 3
            log(f"{indent}{' ' * len(label)}... ({hidden} more)")

    return True


def list_paper_dirs() -> list[str]:
    if not PAPERS_DIR.is_dir():
        return []
    return sorted(
        d.name
        for d in PAPERS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="wrap.py",
        description="Generate semtex-injecting wrappers for fetched "
        "arxiv papers.",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--all",
        action="store_true",
        help="Wrap every paper under papers/",
    )
    g.add_argument(
        "--list",
        action="store_true",
        help="List wrappable papers (those under papers/) and exit.",
    )
    ap.add_argument(
        "--no-rewrite",
        action="store_true",
        dest="no_rewrite",
        help=(
            "Disable the command-rewrite pass (preserve preamble "
            "byte-for-byte). Regression escape valve."
        ),
    )
    ap.add_argument(
        "ids",
        nargs="*",
        help="Specific arxiv IDs to wrap.",
    )
    args = ap.parse_args(argv)

    if args.list:
        for pid in list_paper_dirs():
            print(pid)
        return 0

    if args.all:
        ids = list_paper_dirs()
    else:
        ids = args.ids

    if not ids:
        log(
            "ERROR: no papers specified. Pass arxiv IDs, --all, or "
            "--list. Did you run fetch.py first?"
        )
        return 2

    do_rewrite = not args.no_rewrite
    failures = 0
    for pid in ids:
        if not wrap_paper(pid, do_rewrite=do_rewrite):
            failures += 1

    if failures:
        log(f"\n{failures} of {len(ids)} papers failed to wrap.")
        return 1
    log(f"\nAll {len(ids)} papers wrapped successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
