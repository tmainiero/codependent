#!/usr/bin/env python3
"""
codependent.sty test runner.

Runs every .lvt fixture under unit/ and integration/ through pdflatex
(plus the optional real-world/wrappers/), parses the TEST-* metadata
header in each fixture, applies assertions, and produces a summary.

Designed to run BEFORE codependent.sty's implementation phase: assertions
target observable artifacts (.aux, .cdp, .log, exit code, PDF content)
rather than golden .tlg files. l3build can later replace this runner
once the implementation lands and we can lock in golden output.

Usage:

    python3 scripts/run-tests.py [--filter PATTERN] [--engine pdflatex|lualatex|xelatex]
                         [--keep-temp] [--verbose]
                         [--unit] [--integration] [--visual] [--full]
                         [--unit-only] [--integration-only]
                         [--real-world] [--check-test-index]

System-wide texlive-full is used during the design/test phase per
user direction 2026-04-09 (the project's Nix flake does not yet
include all required packages). The runner detects the system tex
binary at startup and prints a notice. Future runs (post-implementation)
should go through `nix develop` with a flake that has the full deps.

Standard library only. No PyYAML, no requests, no third-party deps.
"""

import argparse
import dataclasses
import difflib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

# ----------------------------------------------------------------------
# Project layout
# ----------------------------------------------------------------------

# Path of THIS script: scripts/run-tests.py (relative to the repo root).
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent  # the codependent repo root
PROJECT_ROOT = REPO_ROOT  # legacy alias retained for in-file readers
TESTFILES_DIR = REPO_ROOT / "testfiles"
UNIT_DIR = TESTFILES_DIR / "unit"
INTEGRATION_DIR = TESTFILES_DIR / "integration"
COMPILED_EXAMPLES_DIR = TESTFILES_DIR / "compiled-examples"
REAL_WORLD_DIR = TESTFILES_DIR / "real-world" / "wrappers"
OUTPUT_DIR = TESTFILES_DIR / "output"

# Where the .sty file lives. The runner copies it into the temp work dir
# so each test sees a clean kpse search path.
STY_FILE = REPO_ROOT / "codependent.sty"
RENDER_STY_FILE = REPO_ROOT / "codependent-render.sty"
LTXML_FILE = REPO_ROOT / "codependent.ltxml"  # may not exist yet


# ----------------------------------------------------------------------
# Test metadata model
# ----------------------------------------------------------------------

METADATA_KEYS = {
    "TEST-NAME": "name",
    "TEST-WHAT": "what",
    "TEST-SOURCE": "source",
    "TEST-SECTION": "section",
    "TEST-BEHAVIOR": "behavior_ids",  # comma-separated B-* IDs from docs/BEHAVIOR.md
    "TEST-PURPOSE": "purpose",
    "TEST-KIND": "kind",
    "TEST-STATUS": "status",
    "TEST-RENDER-MODES": "render_modes",
    "TEST-EXIT": "exit_code",
    "TEST-LOG-NOT": "log_not",  # may repeat
    "TEST-LOG-CONTAINS": "log_contains",  # may repeat
    "TEST-CDP-CONTAINS": "cdp_contains",  # may repeat
    "TEST-CDP-NOT-CONTAINS": "cdp_not_contains",  # may repeat
    "TEST-CDP-COUNT": "cdp_count",  # "<pattern> = <n>", may repeat
    "TEST-CDP-LAST-RECORD": "cdp_last_record",  # last non-empty line must contain this
    "TEST-AUX-CONTAINS": "aux_contains",  # may repeat
    "TEST-AUX-NOT-CONTAINS": "aux_not_contains",  # may repeat
    "TEST-ATOMS-MIN": "atoms_min",
    "TEST-PACKAGES": "packages",
    "TEST-RERUN": "rerun",
    "TEST-PINS-KNOWN-BROKEN": "pins_known_broken",  # 'yes' marks intentional pin
    "TEST-PDF-CONTAINS": "pdf_contains",  # may repeat; text in PDF output
    "TEST-PDF-NOT": "pdf_not",  # may repeat; text must NOT appear in PDF
    "TEST-PDF-LINKS": "pdf_links",  # int; minimum number of internal hyperlinks
    # Structural PDF assertions (require mutool)
    "TEST-PDF-STEXT": "pdf_stext",  # may repeat; regex on mutool stext XML (positions/fonts)
    "TEST-PDF-STEXT-NOT": "pdf_stext_not",  # may repeat; regex must NOT match stext XML
    "TEST-PDF-OBJECTS": "pdf_objects",  # may repeat; regex on mutool show grep (link annots, dests)
    "TEST-PDF-OBJECTS-NOT": "pdf_objects_not",  # may repeat; regex must NOT match objects
    # Object-level PDF link verification (require qpdf --json=2)
    "TEST-PDF-LINK-DEST": "pdf_link_dest",  # may repeat; regex on link destination names
    "TEST-PDF-LINK-DEST-NOT": "pdf_link_dest_not",  # may repeat; dest must NOT exist on any link
    "TEST-PDF-LINK-COUNT": "pdf_link_count",  # exact count of link annotations
    "TEST-PDF-DEST-EXISTS": "pdf_dest_exists",  # may repeat; regex on named destination names
    "TEST-PDF-DEST-NOT-EXISTS": "pdf_dest_not_exists",  # may repeat; named dest must NOT exist
    "TEST-PDF-LINK-RECT": "pdf_link_rect",  # may repeat; "<dest> <x1> <y1> <x2> <y2> <tol>"
    "TEST-PDF-NO-ORPHAN-LINKS": "pdf_no_orphan_links",  # boolean; every link dest must resolve
    # Backref hyperlink verification (require both mutool and qpdf)
    "TEST-PDF-ALL-BACKREFS-LINKED": "pdf_all_backrefs_linked",  # boolean; every Used-in entry must be a hyperlink
    "TEST-PDF-BACKREF-TARGETS": "pdf_backref_targets",  # may repeat; "<atom-dest> = <dest1>, <dest2>, ..."
    "TEST-PDF-BACKREF-ENTRY-TARGET": "pdf_backref_entry_targets",  # may repeat; "<atom_pat> | <entry_text> = <dest_pat>"
    "TEST-PDF-BACKREF-SOURCES-RENDERED": "pdf_backref_sources_rendered",  # boolean; every backref source token must be rendered in PDF
    "TEST-PDF-VSPACE-BETWEEN": "pdf_vspace_between",  # may repeat; "<anchor1-regex> <anchor2-regex> <max-points>" (use shell-style quoting for spaces)
    # PDF y-coordinate and page assertions (require both mutool and qpdf)
    "TEST-PDF-LINK-Y-NEAR": "pdf_link_y_near",   # may repeat; "<source-text> | <anchor-text> | within=<Δpt>"
    "TEST-PDF-LINK-Y-BETWEEN": "pdf_link_y_between",  # may repeat; "<source-text> | <top-text> | <bottom-text>"
    "TEST-PDF-DEST-PAGE": "pdf_dest_page",         # may repeat; "<dest-name> | <anchor-text>"
    "TEST-PDF-PAGES": "pdf_pages",                 # exact PDF page count
    # Package error/warning assertions
    "TEST-EXPECT-PACKAGE-WARNING": "expect_package_warning",  # may repeat; regex on "Package codependent Warning:" line
    "TEST-EXPECT-PACKAGE-ERROR": "expect_package_error",      # may repeat; regex on "Package codependent Error:" line; also drops -halt-on-error
    # Appendix entry assertions (require appendix mode, P05)
    "TEST-PDF-APPENDIX-ENTRY": "pdf_appendix_entry",           # may repeat; "<atom-key> = <display-number> [<printed-kind>]"; requires hyperref + named dest
    "TEST-PDF-APPENDIX-ENTRY-TEXT-ONLY": "pdf_appendix_entry_text_only",  # may repeat; same format; text-only (no dest check)
    "TEST-APPENDIX-ENUM-WAIVER": "appendix_enum_waiver",       # reason string; suppresses enumeration-count guard
    # Three-phase pass-count directives (P01-B)
    "TEST-PASS-COUNT-COLD": "pass_count_cold",      # int; max passes in cold phase
    "TEST-PASS-COUNT-WARM": "pass_count_warm",      # int; max passes in warm phase
    "TEST-PASS-COUNT-WARM-CHANGED": "pass_count_warm_changed",  # int; max passes in warm-changed phase
    "TEST-WARM-MUTATION": "warm_mutation",          # shell command run between warm and warm-changed phases
    "TEST-STABLE-AT": "stable_at",                  # int; phase-qualifiable; declares pass count + asserts convergence
    "TEST-ALLOW-UNDEFINED-REFS": "allow_undefined_refs",  # boolean; waive universal undefined-ref checks with nearby rationale comment
    # Census instrumentation (SW5c commit 1)
    "TEST-CENSUS": "census",
    "TEST-CENSUS-PASS": "census_pass",
}

REPEATING_KEYS = {
    "log_not", "log_contains",
    "cdp_contains", "cdp_not_contains", "cdp_count",
    "aux_contains", "aux_not_contains",
    "pdf_contains", "pdf_not",
    "pdf_stext", "pdf_stext_not",
    "pdf_objects", "pdf_objects_not",
    "pdf_link_dest", "pdf_link_dest_not",
    "pdf_dest_exists", "pdf_dest_not_exists",
    "pdf_link_rect",
    "pdf_backref_targets",
    "pdf_backref_entry_targets",
    "pdf_vspace_between",
    "pdf_link_y_near", "pdf_link_y_between", "pdf_dest_page",
    "expect_package_warning", "expect_package_error",
    "pdf_appendix_entry", "pdf_appendix_entry_text_only",
}

# No-op definitions for l3build regression-test markers.  l3build provides
# these via regression-test.tex; our standalone runner does not load that
# file.  We prepend these \def primitives so \START / \END (and friends) are
# harmless rather than fatal.  \def is a TeX primitive available before any
# LaTeX kernel code, so it is safe above \documentclass.
INJECT_L3BUILD_NOOPS = (
    "% ---- l3build regression-test marker no-ops"
    " (injected by run-tests.py) ----\n"
    "\\def\\START{}\n"
    "\\def\\END{}\n"
    "\\def\\OMIT{}\n"
    "\\def\\OMITS{}\n"
    "\\def\\TIMO{}\n"
    "\\long\\def\\TEST#1#2{}\n"
    "% ---- end l3build no-op injection ----\n"
)


def _load_max_pass_counts() -> dict:
    """Load MAX_PASS_COUNT ratchet values from baseline-sizes.json."""
    baseline = PROJECT_ROOT / ".claude" / "baseline-sizes.json"
    try:
        data = json.loads(baseline.read_text(encoding="utf-8"))
        return {
            "cold": int(data.get("max_pass_count_cold", 2)),
            "warm": int(data.get("max_pass_count_warm", 1)),
            "warm_changed": int(data.get("max_pass_count_warm_changed", 2)),
        }
    except Exception:
        return {"cold": 2, "warm": 1, "warm_changed": 2}


# Loaded at import time; parse_fixture uses these to hard-error early.
MAX_PASS_COUNTS: dict = _load_max_pass_counts()


def parse_test_kind_headers(path: Path) -> dict:
    """Parse shared TEST-KIND metadata via test_header_parser.py.

    Kept as a runner-level entry point for importlib consumers while the
    implementation lives in a tiny shared module.
    """

    parser_path = SCRIPT_DIR / "test_header_parser.py"
    spec = importlib.util.spec_from_file_location("codep_test_header_parser", parser_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load TEST-* parser from {parser_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_test_kind_headers(path)


def _load_test_index_regenerator():
    """Load .claude/scripts/regenerate_test_index.py without package imports."""

    regenerator_path = PROJECT_ROOT / ".claude" / "scripts" / "regenerate_test_index.py"
    spec = importlib.util.spec_from_file_location("codep_regenerate_test_index", regenerator_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load test-index regenerator from {regenerator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sync_test_index(check: bool = False) -> int:
    """Run the generated index preflight.

    Normal dev invocations repair testfiles/test-index.md on drift. CI invokes
    this with check=True, which reports the diff and exits before fixture
    execution without writing.
    """

    try:
        regenerator = _load_test_index_regenerator()
    except Exception as exc:
        sys.stderr.write(f"FATAL: failed to load test-index regenerator: {exc}\n")
        return 2
    return regenerator.regenerate(check=check)


@dataclasses.dataclass
class Fixture:
    path: Path
    name: str
    what: str = ""
    source: str = ""
    section: str = ""
    behavior_ids: list = dataclasses.field(default_factory=list)
    purpose: str = ""
    kind: str = ""
    status: str = ""
    render_modes: str = ""
    exit_code: int = 0
    log_not: list = dataclasses.field(default_factory=list)
    log_contains: list = dataclasses.field(default_factory=list)
    cdp_contains: list = dataclasses.field(default_factory=list)
    cdp_not_contains: list = dataclasses.field(default_factory=list)
    cdp_count: list = dataclasses.field(default_factory=list)
    cdp_last_record: str = ""
    aux_contains: list = dataclasses.field(default_factory=list)
    aux_not_contains: list = dataclasses.field(default_factory=list)
    atoms_min: int = 0
    packages: list = dataclasses.field(default_factory=list)
    rerun: int = 2
    pins_known_broken: bool = False
    pdf_contains: list = dataclasses.field(default_factory=list)
    pdf_not: list = dataclasses.field(default_factory=list)
    pdf_links: int = 0
    pdf_stext: list = dataclasses.field(default_factory=list)
    pdf_stext_not: list = dataclasses.field(default_factory=list)
    pdf_objects: list = dataclasses.field(default_factory=list)
    pdf_objects_not: list = dataclasses.field(default_factory=list)
    # Object-level PDF link verification (qpdf --json=2)
    pdf_link_dest: list = dataclasses.field(default_factory=list)
    pdf_link_dest_not: list = dataclasses.field(default_factory=list)
    pdf_link_count: int = -1  # -1 = not specified
    pdf_dest_exists: list = dataclasses.field(default_factory=list)
    pdf_dest_not_exists: list = dataclasses.field(default_factory=list)
    pdf_link_rect: list = dataclasses.field(default_factory=list)
    pdf_no_orphan_links: bool = False
    # Backref hyperlink verification
    pdf_all_backrefs_linked: bool = False
    pdf_backref_targets: list = dataclasses.field(default_factory=list)
    pdf_backref_entry_targets: list = dataclasses.field(default_factory=list)
    pdf_backref_sources_rendered: bool = False
    pdf_vspace_between: list = dataclasses.field(default_factory=list)
    # PDF y-coordinate and page assertions (B-API-TEST-RUNNER-PDF-Y)
    pdf_link_y_near: list = dataclasses.field(default_factory=list)
    pdf_link_y_between: list = dataclasses.field(default_factory=list)
    pdf_dest_page: list = dataclasses.field(default_factory=list)
    pdf_pages: int = -1
    # Package error/warning assertions
    expect_package_warning: list = dataclasses.field(default_factory=list)
    expect_package_error: list = dataclasses.field(default_factory=list)
    # Appendix entry assertions (P05 appendix mode)
    pdf_appendix_entry: list = dataclasses.field(default_factory=list)
    pdf_appendix_entry_text_only: list = dataclasses.field(default_factory=list)
    appendix_enum_waiver: str = ""
    # Three-phase pass-count (P01-B)
    pass_count_cold: int = 0
    pass_count_warm: int = 0
    pass_count_warm_changed: int = 0
    warm_mutation: str = ""
    stable_at: int = 0  # unqualified TEST-STABLE-AT; phase-qualified variants live in phase_assertions
    allow_undefined_refs: bool = False
    census: bool = False
    census_pass: bool = False
    # Phase-qualified assertion overrides: {"cold": {"log_contains": [...], "stable_at": N, ...}}
    # Keys match METADATA_KEYS attribute names; non-repeating int fields stored directly.
    phase_assertions: dict = dataclasses.field(default_factory=dict)
    # Parse-time error (set by mutual-exclusion guard; causes immediate test failure)
    parse_error: str = ""


def parse_fixture(path: Path) -> Fixture:
    """Parse the TEST-* header comment metadata from a fixture source file."""
    fix = Fixture(path=path, name=path.stem)
    # Optional [phase] qualifier: TEST-FOO[cold]: val or TEST-FOO: val
    header_re = re.compile(
        r"^%{1,2}\s+(TEST-[A-Z0-9-]+)(?:\[(cold|warm|warm_changed)\])?:\s*(.*)$"
    )
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.startswith("%"):
                # First non-metadata line ends the header. We allow blank
                # comment lines but stop on actual LaTeX content.
                if line.strip().startswith("\\") or not line.strip().startswith("%"):
                    break
                continue
            m = header_re.match(line)
            if not m:
                continue
            key = m.group(1)
            phase = m.group(2)   # None or "cold" / "warm" / "warm_changed"
            value = m.group(3).strip()
            attr = METADATA_KEYS.get(key)
            if attr is None:
                continue

            # Phase-qualified directive: store in phase_assertions dict.
            if phase is not None:
                ph = fix.phase_assertions.setdefault(phase, {})
                if attr in REPEATING_KEYS:
                    ph.setdefault(attr, []).append(value)
                elif attr == "stable_at":
                    try:
                        ph["stable_at"] = int(value)
                    except ValueError:
                        pass
                else:
                    ph[attr] = value
                continue

            # Unqualified directive: existing handling.
            if attr == "exit_code":
                try:
                    fix.exit_code = int(value)
                except ValueError:
                    pass
            elif attr == "pdf_links":
                try:
                    fix.pdf_links = int(value)
                except ValueError:
                    pass
            elif attr == "pdf_link_count":
                try:
                    fix.pdf_link_count = int(value)
                except ValueError:
                    pass
            elif attr == "pdf_pages":
                try:
                    fix.pdf_pages = int(value)
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
            elif attr == "pass_count_cold":
                try:
                    fix.pass_count_cold = int(value)
                    if fix.pass_count_cold > MAX_PASS_COUNTS["cold"]:
                        fix.parse_error = (
                            f"TEST-PASS-COUNT-COLD: {fix.pass_count_cold} exceeds "
                            f"max {MAX_PASS_COUNTS['cold']} "
                            f"(see .claude/baseline-sizes.json max_pass_count_cold)"
                        )
                except ValueError:
                    pass
            elif attr == "pass_count_warm":
                try:
                    fix.pass_count_warm = int(value)
                    if fix.pass_count_warm > MAX_PASS_COUNTS["warm"]:
                        fix.parse_error = (
                            f"TEST-PASS-COUNT-WARM: {fix.pass_count_warm} exceeds "
                            f"max {MAX_PASS_COUNTS['warm']} "
                            f"(see .claude/baseline-sizes.json max_pass_count_warm)"
                        )
                except ValueError:
                    pass
            elif attr == "pass_count_warm_changed":
                try:
                    fix.pass_count_warm_changed = int(value)
                    if fix.pass_count_warm_changed > MAX_PASS_COUNTS["warm_changed"]:
                        fix.parse_error = (
                            f"TEST-PASS-COUNT-WARM-CHANGED: {fix.pass_count_warm_changed} "
                            f"exceeds max {MAX_PASS_COUNTS['warm_changed']} "
                            f"(see .claude/baseline-sizes.json max_pass_count_warm_changed)"
                        )
                except ValueError:
                    pass
            elif attr == "stable_at":
                try:
                    fix.stable_at = int(value)
                except ValueError:
                    pass
            elif attr == "packages":
                fix.packages = [p.strip() for p in value.split(",") if p.strip()]
            elif attr == "behavior_ids":
                fix.behavior_ids = [b.strip() for b in value.split(",") if b.strip()]
            elif attr == "pins_known_broken":
                fix.pins_known_broken = value.lower() in ("yes", "true", "1")
            elif attr == "pdf_no_orphan_links":
                fix.pdf_no_orphan_links = value.lower() in ("yes", "true", "1")
            elif attr == "pdf_all_backrefs_linked":
                fix.pdf_all_backrefs_linked = value.lower() in ("yes", "true", "1")
            elif attr == "pdf_backref_sources_rendered":
                fix.pdf_backref_sources_rendered = value.lower() in ("yes", "true", "1")
            elif attr == "allow_undefined_refs":
                fix.allow_undefined_refs = value.lower() in ("yes", "true", "1")
            elif attr in {"census", "census_pass"}:
                setattr(fix, attr, value.lower() in ("yes", "true", "1", "enabled", "on"))
            elif attr in REPEATING_KEYS:
                getattr(fix, attr).append(value)
            else:
                setattr(fix, attr, value)

    if fix.pdf_appendix_entry and fix.pdf_appendix_entry_text_only:
        fix.parse_error = (
            "TEST-PDF-APPENDIX-ENTRY and TEST-PDF-APPENDIX-ENTRY-TEXT-ONLY "
            "are mutually exclusive in the same fixture"
        )
    if fix.pass_count_warm_changed > 0 and not fix.warm_mutation:
        fix.parse_error = (
            "TEST-PASS-COUNT-WARM-CHANGED declared but no TEST-WARM-MUTATION command"
        )
    if fix.census_pass:
        fix.census = True
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
# PDF tool detection (for TEST-PDF-* directives)
# ----------------------------------------------------------------------

# Prefer mutool (mupdf); fall back to pdftotext (poppler).
PDF_TEXT_TOOL: str | None = shutil.which("mutool") or shutil.which("pdftotext")
PDF_LINK_TOOL: str | None = shutil.which("mutool") or shutil.which("qpdf")
# Structural assertions (stext positions/fonts, PDF objects) require mutool.
PDF_STEXT_TOOL: str | None = shutil.which("mutool")
# Object-level link verification requires qpdf >= 11.0 (--json=2).
PDF_QPDF_TOOL: str | None = shutil.which("qpdf")


def _extract_pdf_text(pdf_path: Path) -> str | None:
    """Extract plain text from a PDF.  Returns None if no tool available."""
    if PDF_TEXT_TOOL is None:
        return None
    tool_name = Path(PDF_TEXT_TOOL).name
    try:
        if tool_name == "mutool":
            proc = subprocess.run(
                [PDF_TEXT_TOOL, "draw", "-F", "text", "-o", "-", str(pdf_path)],
                capture_output=True, text=True, timeout=30,
            )
        else:  # pdftotext
            proc = subprocess.run(
                [PDF_TEXT_TOOL, str(pdf_path), "-"],
                capture_output=True, text=True, timeout=30,
            )
        if proc.returncode == 0:
            return proc.stdout
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _extract_pdf_stext(pdf_path: Path) -> str | None:
    """Extract structured text XML from a PDF (mutool only).

    The stext format includes per-character x,y coordinates and font names,
    enabling assertions on text position (flush-left vs indented) and font
    (backref text in configured font vs body font).
    """
    if PDF_STEXT_TOOL is None:
        return None
    try:
        proc = subprocess.run(
            [PDF_STEXT_TOOL, "draw", "-F", "stext", "-o", "-", str(pdf_path)],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


@dataclasses.dataclass
class _StextBlock:
    page_index: int
    page_height: float
    first_line_text: str
    bbox: list[float]


def _parse_bbox(bbox_text: str | None) -> list[float] | None:
    if not bbox_text:
        return None
    try:
        bbox = [float(part) for part in bbox_text.split()]
    except ValueError:
        return None
    return bbox if len(bbox) == 4 else None


def _union_bboxes(bboxes: list[list[float]]) -> list[float] | None:
    if not bboxes:
        return None
    return [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ]


def _parse_stext_blocks(stext_xml: str) -> list[_StextBlock]:
    """Parse mutool stext XML into document-order blocks with first-line text."""
    try:
        root = ElementTree.fromstring(stext_xml)
    except ElementTree.ParseError:
        return []

    blocks: list[_StextBlock] = []
    for page_index, page in enumerate(root.findall(".//page")):
        try:
            page_height = float(page.attrib.get("height", "792"))
        except ValueError:
            page_height = 792.0
        for block in page.findall("./block"):
            line_nodes = block.findall(".//line")
            if not line_nodes:
                continue
            first_line_text = (line_nodes[0].attrib.get("text") or "").strip()
            if not first_line_text:
                continue
            block_bbox = _parse_bbox(block.attrib.get("bbox"))
            if block_bbox is None:
                line_bboxes = [
                    bbox
                    for bbox in (_parse_bbox(line.attrib.get("bbox")) for line in line_nodes)
                    if bbox is not None
                ]
                block_bbox = _union_bboxes(line_bboxes)
            if block_bbox is None:
                continue
            blocks.append(
                _StextBlock(
                    page_index=page_index,
                    page_height=page_height,
                    first_line_text=first_line_text,
                    bbox=block_bbox,
                )
            )
    return blocks


def _parse_pdf_vspace_between_spec(spec: str) -> tuple[str, str, float] | None:
    """Parse TEST-PDF-VSPACE-BETWEEN using shell-style quoting for regexes."""
    try:
        parts = shlex.split(spec)
    except ValueError:
        return None
    if len(parts) != 3:
        return None
    try:
        max_points = float(parts[2])
    except ValueError:
        return None
    return parts[0], parts[1], max_points


def _measure_pdf_vspace_between(
    stext_xml: str,
    anchor1_regex: str,
    anchor2_regex: str,
) -> tuple[float | None, str | None]:
    """Measure vertical gap between two stext blocks matched by first-line regex."""
    blocks = _parse_stext_blocks(stext_xml)
    try:
        anchor1_re = re.compile(anchor1_regex)
        anchor2_re = re.compile(anchor2_regex)
    except re.error as exc:
        return None, f"invalid regex ({exc})"

    block1 = next((block for block in blocks if anchor1_re.search(block.first_line_text)), None)
    if block1 is None:
        return None, f"anchor not found: {anchor1_regex}"
    block2 = next((block for block in blocks if anchor2_re.search(block.first_line_text)), None)
    if block2 is None:
        return None, f"anchor not found: {anchor2_regex}"

    if block1.page_index != block2.page_index:
        return 0.0, None

    gap = max(0.0, block2.bbox[1] - block1.bbox[3])
    return gap, None


def _find_stext_line_for_text(
    stext_xml: str,
    text_regex: str,
) -> "tuple[list[float], float, int] | None":
    """Find the first stext <line> whose text attribute matches text_regex.

    Returns (bbox [x1, y1_topdown, x2, y2_topdown], page_height, page_index)
    in stext top-down coordinates, or None if not found.
    """
    try:
        root = ElementTree.fromstring(stext_xml)
    except ElementTree.ParseError:
        return None
    try:
        pat = re.compile(text_regex)
    except re.error:
        return None
    for page_idx, page in enumerate(root.findall(".//page")):
        try:
            ph = float(page.attrib.get("height", "792"))
        except ValueError:
            ph = 792.0
        for block in page.findall("./block"):
            for line in block.findall(".//line"):
                text = (line.attrib.get("text") or "").strip()
                if pat.search(text):
                    bbox_str = line.attrib.get("bbox", "")
                    try:
                        bbox = [float(x) for x in bbox_str.split()]
                    except ValueError:
                        continue
                    if len(bbox) == 4:
                        return (bbox, ph, page_idx)
    return None


def _find_link_for_source_text(
    link_data: "PdfLinkObjects",
    stext_xml: str,
    source_regex: str,
) -> "PdfLinkInfo | None":
    """Find the first link annotation whose source text matches source_regex.

    Locates the text via stext bboxes then finds overlapping link annotations.
    """
    result = _find_stext_line_for_text(stext_xml, source_regex)
    if result is None:
        return None
    bbox, page_height, _page_idx = result
    bline = _BackrefLine(text="", entries=[], bbox=bbox, page_height=page_height)
    overlapping = _links_overlapping_line(link_data, bline)
    return overlapping[0] if overlapping else None


def _extract_pdf_objects(pdf_path: Path) -> str | None:
    """Dump all PDF objects as text (mutool only).

    The output includes link annotations (/Subtype /Link), their destinations
    (/Dest or /A << /S /GoTo /D ... >>), and named destinations.  Regex
    assertions against this output can verify that hyperlinks point to the
    correct anchors (e.g., theorem anchors vs equation anchors).
    """
    if PDF_STEXT_TOOL is None:
        return None
    try:
        proc = subprocess.run(
            [PDF_STEXT_TOOL, "show", str(pdf_path), "grep"],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _count_pdf_links(pdf_path: Path) -> int | None:
    """Count internal hyperlink annotations in a PDF.

    Returns the count, or None if no suitable tool is available.
    """
    if PDF_LINK_TOOL is None:
        return None
    tool_name = Path(PDF_LINK_TOOL).name
    try:
        if tool_name == "mutool":
            # `mutool show <file> grep` outputs every PDF object in text
            # form.  We count lines containing "/Subtype/Link" (mutool
            # omits spaces between name tokens in its compact output).
            proc = subprocess.run(
                [PDF_LINK_TOOL, "show", str(pdf_path), "grep"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return None
            # Handle both "/Subtype/Link" (mutool compact) and
            # "/Subtype /Link" (older mutool or other tools).
            count = proc.stdout.count("/Subtype/Link")
            if count == 0:
                count = proc.stdout.count("/Subtype /Link")
            return count
        else:  # qpdf
            proc = subprocess.run(
                [PDF_LINK_TOOL, str(pdf_path), "--show-pages",
                 "--with-images"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                # Fall back to listing all objects and grepping for /Link
                proc2 = subprocess.run(
                    [PDF_LINK_TOOL, str(pdf_path), "--list-objects"],
                    capture_output=True, text=True, timeout=30,
                )
                if proc2.returncode != 0:
                    return None
                return proc2.stdout.count("/Link")
            return proc.stdout.count("/Link")
    except (subprocess.TimeoutExpired, OSError):
        return None


def _count_pdf_pages(pdf_path: Path) -> int | None:
    """Return the exact page count using qpdf, or None if unavailable."""
    if PDF_QPDF_TOOL is None:
        return None
    try:
        proc = subprocess.run(
            [PDF_QPDF_TOOL, "--show-npages", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


@dataclasses.dataclass
class PdfLinkInfo:
    """A single link annotation extracted from PDF objects."""
    obj_id: str
    rect: list  # [x1, y1, x2, y2]
    dest: str   # destination name (e.g. "u:lemma.8")


@dataclasses.dataclass
class PdfDestData:
    """Named destination data extracted from qpdf JSON."""
    page_ref: str        # page object reference string e.g. "5 0 R"
    y_pdf: float | None  # PDF bottom-up y-coordinate, or None for /Fit destinations


@dataclasses.dataclass
class PdfLinkObjects:
    """Structured PDF link/destination data extracted via qpdf --json=2."""
    links: list   # list of PdfLinkInfo
    destinations: set  # set of named destination strings
    dest_data: dict = dataclasses.field(default_factory=dict)  # dict[str, PdfDestData]
    page_ref_to_index: dict = dataclasses.field(default_factory=dict)  # dict[str, int]


def _collect_names_from_tree(objs: dict, obj_ref: str, visited: set) -> list[str]:
    """Recursively collect named destination strings from a PDF Names tree.

    The Names tree can have leaf nodes (/Names array with /Limits) and
    intermediate nodes (/Kids array pointing to child nodes).  Object
    references in qpdf JSON v2 are bare strings like "25 0 R".
    """
    if obj_ref in visited:
        return []
    visited.add(obj_ref)
    key = f"obj:{obj_ref}"
    node = objs.get(key)
    if not isinstance(node, dict):
        return []
    val = node.get("value", {})
    if not isinstance(val, dict):
        return []

    names: list[str] = []
    # Leaf node: /Names is [name1, ref1, name2, ref2, ...]
    names_arr = val.get("/Names")
    if isinstance(names_arr, list):
        for i in range(0, len(names_arr), 2):
            if i < len(names_arr) and isinstance(names_arr[i], str):
                names.append(names_arr[i])

    # Intermediate node: /Kids is [ref1, ref2, ...]
    kids = val.get("/Kids")
    if isinstance(kids, list):
        for kid_ref in kids:
            if isinstance(kid_ref, str):
                names.extend(_collect_names_from_tree(objs, kid_ref, visited))

    return names


def _find_names_root(objs: dict) -> str | None:
    """Find the Dests Names tree root object reference.

    The catalog object has /Names -> obj with /Dests -> tree root.
    """
    for key, val in objs.items():
        if not isinstance(val, dict):
            continue
        v = val.get("value", {})
        if not isinstance(v, dict):
            continue
        # Catalog has /Type /Catalog and /Names pointing to a names dict
        if v.get("/Type") == "/Catalog":
            names_ref = v.get("/Names")
            if isinstance(names_ref, str):
                # Resolve the names dict object
                names_obj = objs.get(f"obj:{names_ref}")
                if isinstance(names_obj, dict):
                    names_val = names_obj.get("value", {})
                    if isinstance(names_val, dict):
                        dests_ref = names_val.get("/Dests")
                        if isinstance(dests_ref, str):
                            return dests_ref
    return None


def _parse_dest_array(dest_val) -> tuple[str | None, float | None]:
    """Extract (page_ref, y_pdf) from a PDF destination value.

    Handles both array form [page_ref, /FitType, ...] and dict form {/D: [...]}.
    Returns (page_ref, y_pdf) where y_pdf is PDF bottom-up coords, or None for /Fit.
    """
    if isinstance(dest_val, dict):
        dest_val = dest_val.get("/D")
    if not isinstance(dest_val, list) or len(dest_val) < 2:
        return None, None
    page_ref = dest_val[0] if isinstance(dest_val[0], str) else None
    fit_type = dest_val[1] if isinstance(dest_val[1], str) else None
    y_pdf = None
    if fit_type == "/XYZ" and len(dest_val) >= 4:
        try:
            v = dest_val[3]
            y_pdf = float(v) if v is not None else None
        except (TypeError, ValueError):
            pass
    elif fit_type == "/FitH" and len(dest_val) >= 3:
        try:
            v = dest_val[2]
            y_pdf = float(v) if v is not None else None
        except (TypeError, ValueError):
            pass
    return page_ref, y_pdf


def _collect_dest_data_from_tree(
    objs: dict,
    obj_ref: str,
    visited: set,
) -> list[tuple[str, str, float | None]]:
    """Collect (dest_name, page_ref, y_pdf) tuples from a PDF Names tree.

    Extends _collect_names_from_tree to also resolve each destination object,
    extracting the page reference and y-coordinate for spatial assertions.
    """
    if obj_ref in visited:
        return []
    visited.add(obj_ref)
    key = f"obj:{obj_ref}"
    node = objs.get(key)
    if not isinstance(node, dict):
        return []
    val = node.get("value", {})
    if not isinstance(val, dict):
        return []

    results: list[tuple[str, str, float | None]] = []
    names_arr = val.get("/Names")
    if isinstance(names_arr, list):
        i = 0
        while i + 1 < len(names_arr):
            name = names_arr[i]
            dest_ref = names_arr[i + 1]
            i += 2
            if not isinstance(name, str):
                continue
            dest_val = None
            if isinstance(dest_ref, str):
                dest_obj = objs.get(f"obj:{dest_ref}")
                if isinstance(dest_obj, dict):
                    dest_val = dest_obj.get("value")
            elif isinstance(dest_ref, list):
                dest_val = dest_ref
            page_ref, y_pdf = _parse_dest_array(dest_val)
            results.append((name, page_ref or "", y_pdf))

    kids = val.get("/Kids")
    if isinstance(kids, list):
        for kid_ref in kids:
            if isinstance(kid_ref, str):
                results.extend(_collect_dest_data_from_tree(objs, kid_ref, visited))

    return results


def _collect_page_refs(objs: dict, node_ref: str, visited: set) -> list[str]:
    """Recursively collect leaf page object refs in document order from the page tree."""
    if node_ref in visited:
        return []
    visited.add(node_ref)
    key = f"obj:{node_ref}"
    node = objs.get(key)
    if not isinstance(node, dict):
        return []
    val = node.get("value", {})
    if not isinstance(val, dict):
        return []
    if val.get("/Type") == "/Page":
        return [node_ref]
    kids = val.get("/Kids")
    if isinstance(kids, list):
        result: list[str] = []
        for kid_ref in kids:
            if isinstance(kid_ref, str):
                result.extend(_collect_page_refs(objs, kid_ref, visited))
        return result
    return []


def _build_page_ref_to_index(objs: dict) -> dict[str, int]:
    """Build {page_ref: 0-based-index} by traversing the page tree from catalog."""
    pages_root: str | None = None
    for val_container in objs.values():
        if not isinstance(val_container, dict):
            continue
        v = val_container.get("value", {})
        if not isinstance(v, dict):
            continue
        if v.get("/Type") == "/Catalog":
            ref = v.get("/Pages")
            if isinstance(ref, str):
                pages_root = ref
                break
    if pages_root is None:
        return {}
    page_refs = _collect_page_refs(objs, pages_root, set())
    return {ref: idx for idx, ref in enumerate(page_refs)}


def _extract_pdf_link_objects(pdf_path: Path) -> PdfLinkObjects | None:
    """Extract link annotations and named destinations via qpdf --json=2.

    Returns a PdfLinkObjects with structured link and destination data,
    or None if qpdf is unavailable or extraction fails.
    """
    if PDF_QPDF_TOOL is None:
        return None
    try:
        proc = subprocess.run(
            [PDF_QPDF_TOOL, str(pdf_path), "--json=2"],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None

    qpdf_arr = data.get("qpdf")
    if not isinstance(qpdf_arr, list) or len(qpdf_arr) < 2:
        return None
    objs = qpdf_arr[1]
    if not isinstance(objs, dict):
        return None

    # Collect link annotations.
    links: list[PdfLinkInfo] = []
    for key, val in objs.items():
        if not isinstance(val, dict):
            continue
        v = val.get("value", {})
        if not isinstance(v, dict):
            continue
        if v.get("/Subtype") != "/Link":
            continue
        rect = v.get("/Rect", [])
        # Determine destination: /A << /S /GoTo /D "dest" >> or /Dest "dest"
        dest = None
        action = v.get("/A")
        if isinstance(action, dict):
            d = action.get("/D")
            if isinstance(d, str):
                dest = d
            elif isinstance(d, list) and len(d) > 0 and isinstance(d[0], str):
                # Array form: [page_ref, /Fit...] — not a named dest
                dest = None
        if dest is None:
            d = v.get("/Dest")
            if isinstance(d, str):
                dest = d
            elif isinstance(d, list) and len(d) > 0 and isinstance(d[0], str):
                dest = None
        links.append(PdfLinkInfo(
            obj_id=key,
            rect=rect if isinstance(rect, list) else [],
            dest=dest or "",
        ))

    # Collect named destinations from the Names tree (names + dest data).
    destinations: set[str] = set()
    dest_data: dict[str, PdfDestData] = {}
    dests_root = _find_names_root(objs)
    if dests_root is not None:
        visited: set[str] = set()
        dest_items = _collect_dest_data_from_tree(objs, dests_root, visited)
        for name, page_ref, y_pdf in dest_items:
            destinations.add(name)
            dest_data[name] = PdfDestData(page_ref=page_ref, y_pdf=y_pdf)

    page_ref_to_index = _build_page_ref_to_index(objs)

    return PdfLinkObjects(
        links=links,
        destinations=destinations,
        dest_data=dest_data,
        page_ref_to_index=page_ref_to_index,
    )


# ----------------------------------------------------------------------
# Backref hyperlink verification helpers
# ----------------------------------------------------------------------


@dataclasses.dataclass
class _BackrefLine:
    """A single 'Used in ...' line extracted from stext, with position info."""
    text: str         # full line text e.g. "Used in 1.4, 1.5, 1.5*, 2.1."
    entries: list     # individual backref entries e.g. ["1.4", "1.5", "1.5*", "2.1"]
    bbox: list        # [x1_stext, y1_stext, x2_stext, y2_stext] (top-down coords)
    page_height: float
    # Per-character x-ranges: list of (char_str, x_left, x_right) in stext coords.
    # Populated by _parse_backref_lines_from_stext for entry-level link matching.
    char_xranges: list = dataclasses.field(default_factory=list)


def _parse_backref_lines_from_stext(stext_xml: str) -> list[_BackrefLine]:
    """Parse all 'Used in ...' lines from stext XML output.

    Returns a list of _BackrefLine with text, entry list, and bbox.
    The stext coordinate system has y=0 at top; we store both the raw
    bbox and the page height so callers can convert to PDF coords (y=0
    at bottom).  Handles multi-page documents by tracking per-page heights.
    """
    results = []

    # Build a list of (page_start_offset, page_height) for each page.
    page_re = re.compile(r'<page[^>]+height="([^"]+)"')
    page_positions = []  # (char_offset, height)
    for pm in page_re.finditer(stext_xml):
        try:
            h = float(pm.group(1))
        except ValueError:
            h = 792.0
        page_positions.append((pm.start(), h))
    if not page_positions:
        page_positions.append((0, 792.0))

    def _page_height_at(offset: int) -> float:
        """Return the page height for a match at the given char offset."""
        height = page_positions[0][1]
        for pos, h in page_positions:
            if pos > offset:
                break
            height = h
        return height

    # Find all <line> elements containing "Used in" — full block including </line>
    line_block_re = re.compile(
        r'<line\s+bbox="([^"]+)"[^>]*text="([^"]*Used in[^"]*)"[^>]*>(.*?)</line>',
        re.DOTALL,
    )
    # Regex to extract per-character positions from <char> elements.
    # quad="x0 y0 x1 y1 x2 y2 x3 y3" encodes 4 corners; x0 is left edge, x2/x1 is right.
    char_re = re.compile(r'<char\s+quad="([^"]+)"[^>]*\bc="([^"]*)"')

    for m in line_block_re.finditer(stext_xml):
        bbox_str = m.group(1)
        text = m.group(2)
        inner_xml = m.group(3)
        # Extract the "Used in ..." portion from the full line text.
        ui_idx = text.find("Used in")
        if ui_idx < 0:
            continue
        text = text[ui_idx:]
        try:
            bbox = [float(x) for x in bbox_str.split()]
        except ValueError:
            continue
        if len(bbox) != 4:
            continue

        page_height = _page_height_at(m.start())

        # Parse individual backref entries from the text.
        # Format: "Used in 1.4, 1.5, 1.5*, 2.1, 2.3, 2.4*, 3.4."
        # or "Used in (2.1), 3.2*."
        after_prefix = text[len("Used in "):]  # strip "Used in "
        # Remove trailing period
        if after_prefix.endswith("."):
            after_prefix = after_prefix[:-1]
        # Split on ", " to get individual entries
        entries = [e.strip() for e in after_prefix.split(",") if e.strip()]

        # Extract per-character x-ranges from <char> elements within this line.
        # quad format: "x0 y0 x1 y1 x2 y2 x3 y3" where x0=left, x2=right of glyph.
        char_xranges = []
        for cm in char_re.finditer(inner_xml):
            quad_parts = cm.group(1).split()
            c = cm.group(2)
            if len(quad_parts) >= 3:
                try:
                    x_left = float(quad_parts[0])
                    x_right = float(quad_parts[2])
                    char_xranges.append((c, x_left, x_right))
                except ValueError:
                    pass

        results.append(_BackrefLine(
            text=text,
            entries=entries,
            bbox=bbox,
            page_height=page_height,
            char_xranges=char_xranges,
        ))
    return results


def _links_overlapping_line(
    link_data: "PdfLinkObjects",
    backref_line: _BackrefLine,
) -> list["PdfLinkInfo"]:
    """Find link annotations whose Rect overlaps a backref line's bbox.

    Converts stext coords (top-down) to PDF coords (bottom-up) for
    comparison with link Rects.  Uses the link's vertical midpoint to
    avoid false positives from adjacent lines that barely overlap.
    """
    # Convert stext bbox to PDF coords: PDF_y = page_height - stext_y
    # stext bbox: [x1, y_top, x2, y_bottom] (y increases downward)
    # PDF rect: [x1, y_bottom, x2, y_top] (y increases upward)
    sx1, sy1, sx2, sy2 = backref_line.bbox
    ph = backref_line.page_height
    # PDF coordinates for the line region
    pdf_x1 = sx1
    pdf_x2 = sx2
    pdf_y_bottom = ph - sy2  # bottom of text in PDF coords
    pdf_y_top = ph - sy1     # top of text in PDF coords

    # Allow some tolerance (2 points for edges)
    tol = 2.0
    overlapping = []
    for lnk in link_data.links:
        if len(lnk.rect) != 4:
            continue
        lx1, ly1, lx2, ly2 = lnk.rect
        # Check horizontal overlap: link must start within line's x range
        if lx2 < pdf_x1 - tol or lx1 > pdf_x2 + tol:
            continue
        # Check vertical: link's midpoint must be within line's y range.
        # This avoids false positives from adjacent-line links that
        # partially overlap due to font ascender/descender differences.
        link_y_mid = (ly1 + ly2) / 2.0
        if link_y_mid < pdf_y_bottom - tol or link_y_mid > pdf_y_top + tol:
            continue
        overlapping.append(lnk)
    return overlapping


def _x_range_of_entry_text(
    bline: "_BackrefLine",
    entry_text: str,
) -> tuple[float, float] | None:
    """Find the x-range [x_left, x_right] of entry_text within a backref line.

    Uses char_xranges (populated from stext <char> elements) to find the
    contiguous run of characters matching entry_text as a substring of the
    line's text.  Returns (x_left, x_right) in stext coordinates, or None if
    the substring cannot be located.

    Matching is done by aligning the line's char sequence (ignoring chars with
    zero-width, i.e. kerning/spacing glyphs) against the full line text, then
    locating the offset of entry_text within that text.
    """
    if not bline.char_xranges:
        return None
    line_text = bline.text
    if entry_text not in line_text:
        return None
    # Find all occurrences; we will try to map each to char positions.
    # The char_xranges list was built from ALL chars in the line (including
    # those before "Used in"), but line.text starts at "Used in".  We need
    # to find the char index offset corresponding to the start of "Used in"
    # within the full sequence of chars.

    # Strategy: reconstruct the full concatenation of char characters from
    # char_xranges and align with line_text (which starts at "Used in").
    # The stext line text attribute is the concatenated c attributes of all
    # <char> elements.  We find where our entry_text sits in line_text, then
    # map that back to char indices.

    # Reconstruct text from chars (c attributes joined).
    # line_text starts at "Used in" but char_xranges covers the full stext line.
    chars_text = "".join(c for c, _xl, _xr in bline.char_xranges)

    # Find where line_text starts within chars_text (line_text is a suffix
    # of chars_text starting at "Used in").
    offset = chars_text.find("Used in")
    if offset < 0:
        # Fallback: try direct search from beginning.
        offset = 0

    # Now find entry_text within line_text starting at position 0.
    et_start_in_line = line_text.find(entry_text)
    if et_start_in_line < 0:
        return None

    # Convert to index in chars_text.
    char_start = offset + et_start_in_line
    char_end = char_start + len(entry_text)

    if char_end > len(bline.char_xranges):
        return None

    # Collect x-ranges of chars in [char_start, char_end).
    xs_left = []
    xs_right = []
    for ci in range(char_start, char_end):
        _c, xl, xr = bline.char_xranges[ci]
        if xl < xr:  # skip zero-width glyphs
            xs_left.append(xl)
            xs_right.append(xr)
    if not xs_left:
        return None
    return (min(xs_left), max(xs_right))


def _find_link_for_entry(
    link_data: "PdfLinkObjects",
    bline: "_BackrefLine",
    entry_x_left: float,
    entry_x_right: float,
) -> list["PdfLinkInfo"]:
    """Find link annotations that cover an entry's x-range within a backref line.

    Uses the line's y-range (from bbox) together with the entry's x-range to
    narrow to links whose rectangle overlaps the entry's position.  Coordinates
    are converted from stext (top-down) to PDF (bottom-up) as in
    _links_overlapping_line.
    """
    sx1, sy1, sx2, sy2 = bline.bbox
    ph = bline.page_height
    pdf_y_bottom = ph - sy2
    pdf_y_top = ph - sy1
    tol = 3.0  # slightly wider tolerance for entry-level matching
    result = []
    for lnk in link_data.links:
        if len(lnk.rect) != 4:
            continue
        lx1, ly1, lx2, ly2 = lnk.rect
        # Vertical: link midpoint must be within line y-range.
        link_y_mid = (ly1 + ly2) / 2.0
        if link_y_mid < pdf_y_bottom - tol or link_y_mid > pdf_y_top + tol:
            continue
        # Horizontal: link rect must overlap entry's x-range.
        if lx2 < entry_x_left - tol or lx1 > entry_x_right + tol:
            continue
        result.append(lnk)
    return result


# Regex that matches display-number tokens in "Used in" rows:
# bare N.M, starred N.M*, parenthesised (N.M) or (N.M–N.M) or (N.M-N.M).
_BACKREF_TOKEN_RE = re.compile(
    r"^\(?\d+\.\d+(?:[–\-]\d+\.\d+)?\)?\*?$"
)
# Statement labels rendered in PDF body text (e.g. "Theorem 2.3", "Lemma 1.5").
_RENDERED_STATEMENT_RE = re.compile(
    r"\b(?:Theorem|Lemma|Proposition|Corollary|Definition|Remark|Example|"
    r"Claim|Conjecture|Hypothesis|Observation|Exercise|Problem|Question|"
    r"Notation|Convention)\s+(\d+\.\d+)\b"
)
# Paragraph margin-numbers rendered in the PDF by \codep@emitmargin.
# mutool stext represents these as <line> elements whose text attribute is
# exactly the atom number — e.g. text="2.3" — distinct from bbox/quad
# coordinate attributes (which always contain multiple space-separated floats).
_RENDERED_PARAGRAPH_RE = re.compile(r'\btext="\s*(\d+\.\d+)\s*"')


def _check_backref_sources_rendered(
    backref_lines: "list[_BackrefLine]",
    stext_xml: str,
    fail: "callable",
) -> None:
    """Implement TEST-PDF-BACKREF-SOURCES-RENDERED: yes.

    For each 'Used in' row, tokenise the backref list and verify that every
    display-number token has a corresponding rendered atom in the PDF stext.

    Rules per token class:
    - Starred N.M*  : proof atom; accept if ANY rendered statement bearing
                      number N.M appears in stext (proof inherits parent number).
    - Parenthesised : equation ref; accept if the parenthesised form (N.M)
                      appears literally in stext (equation numbers are rendered
                      inside math mode as "(N.M)").
    - Bare N.M      : theorem/definition/remark/paragraph/etc.; accept if stext
                      contains a statement-heading line like "Theorem N.M" OR a
                      paragraph margin annotation with text exactly "N.M".
    """
    # Pre-compute the set of rendered display numbers from statement headings.
    rendered_statement_nums: set[str] = set()
    for m in _RENDERED_STATEMENT_RE.finditer(stext_xml):
        rendered_statement_nums.add(m.group(1))
    # Pre-compute the set of rendered display numbers from paragraph margin annotations.
    rendered_paragraph_nums: set[str] = set()
    for m in _RENDERED_PARAGRAPH_RE.finditer(stext_xml):
        rendered_paragraph_nums.add(m.group(1))

    for bline in backref_lines:
        # Re-tokenise respecting top-level commas (parens protect ranges).
        raw_text = bline.text
        # Strip "Used in " prefix, trailing period.
        after = raw_text[len("Used in "):]
        if after.endswith("."):
            after = after[:-1]
        # Top-level comma split: track paren depth to avoid splitting inside (N.M–N.M).
        tokens: list[str] = []
        buf = ""
        depth = 0
        for ch in after:
            if ch == "(":
                depth += 1
                buf += ch
            elif ch == ")":
                depth -= 1
                buf += ch
            elif ch == "," and depth == 0:
                tokens.append(buf.strip())
                buf = ""
            else:
                buf += ch
        if buf.strip():
            tokens.append(buf.strip())

        for token in tokens:
            if not _BACKREF_TOKEN_RE.match(token):
                continue  # not a display-number token; skip (e.g. concept names)
            is_starred = token.endswith("*")
            is_paren = token.startswith("(")
            bare = token.rstrip("*").strip("()")

            if is_paren:
                # Equation ref: "(N.M)" or "(N.M–N.M)". Check each endpoint.
                inner = token.strip("()")
                # May be a range "N.M–N.M"; split on en-dash or hyphen.
                endpoints = re.split(r"[–\-]", inner, maxsplit=1)
                all_found = True
                for ep in endpoints:
                    ep = ep.strip()
                    # Equation numbers appear in PDF as "(N.M)" surrounded by parens.
                    # Accept if the parenthesised form appears in PDF text content.
                    paren_form = f"({ep})"
                    if paren_form not in stext_xml:
                        all_found = False
                if not all_found:
                    fail(
                        f"phantom backref source: '{raw_text}' cites {token} "
                        f"but no equation with display {token} is rendered"
                    )
            elif is_starred:
                # Proof atom N.M*: accept if parent display number N.M appears
                # in rendered statement headings (e.g. "Theorem 2.7" in stext).
                # Do NOT match raw stext XML (coordinates embed arbitrary numbers).
                if bare not in rendered_statement_nums:
                    fail(
                        f"phantom backref source: '{raw_text}' cites {token} "
                        f"but no atom with display {bare} is rendered"
                    )
            else:
                # Bare N.M: accept if found in statement headings OR in paragraph
                # margin annotations (union of both detection paths).
                # Do NOT match raw stext XML (coordinates embed arbitrary numbers).
                if bare not in rendered_statement_nums | rendered_paragraph_nums:
                    fail(
                        f"phantom backref source: '{raw_text}' cites {token} "
                        f"but no atom with display {token} is rendered"
                    )


# ----------------------------------------------------------------------
# Appendix entry helpers
# ----------------------------------------------------------------------


def _parse_appendix_entry_spec(spec: str) -> tuple[str, str, str | None] | None:
    """Parse '<atom-key> = <display-number> [<printed-kind>]'.

    Returns (atom_key, display_number, printed_kind) or None on parse error.
    """
    if "=" not in spec:
        return None
    atom_key, rest = spec.split("=", 1)
    atom_key = atom_key.strip()
    rest = rest.strip()
    parts = rest.split(None, 1)
    if not parts:
        return None
    display_number = parts[0]
    printed_kind = parts[1].strip() if len(parts) > 1 else None
    return atom_key, display_number, printed_kind


def _count_appendix_entries_in_pdf(link_data: "PdfLinkObjects") -> int:
    """Count named destinations matching the codep-appendix: namespace."""
    return sum(
        1 for d in link_data.destinations if d.startswith("codep-appendix:")
    )


# ----------------------------------------------------------------------
# Census helpers
# ----------------------------------------------------------------------


CENSUS_ATOMREF_RE = re.compile(r"\\codep@atomref\{([^{}]+)\}\{([^{}]+)\}")
CENSUS_RENDERLIST_RE = re.compile(r"\\codep@renderlist\{([^{}]+)\}\{")
PAGE_BEARING_NEWLABEL_RE = re.compile(
    r"^\\newlabel\{.*\}\{\{.*\}\{[^{}]+\}"
)
PAGE_BEARING_WRITEFILE_RE = re.compile(
    r"^\\@writefile\{(?:toc|lof|lot)\}\{"
)
CENSUS_BOOLEAN_TRUE = {"yes", "true", "1", "enabled", "on"}
CENSUS_MEASURE_KEYS = (
    "atomref_gap",
    "renderlist_first_appearance_after_pass2",
    "page_bearing_diff_pass2_to_pass3",
)


def _census_output_path(name: str) -> Path:
    return OUTPUT_DIR / f"{name}.census.json"


def _extract_atomref_keys(aux_text: str) -> list[str]:
    keys = {
        f"{src}||{tgt}"
        for src, tgt in CENSUS_ATOMREF_RE.findall(aux_text)
    }
    return sorted(keys)


def _extract_renderlist_keys(aux_text: str) -> list[str]:
    return sorted(set(CENSUS_RENDERLIST_RE.findall(aux_text)))


def _extract_page_bearing_lines(aux_text: str) -> list[str]:
    lines = []
    for line in aux_text.splitlines():
        if PAGE_BEARING_NEWLABEL_RE.search(line) or PAGE_BEARING_WRITEFILE_RE.search(line):
            lines.append(line)
    return sorted(lines)


def _page_bearing_diff(before: list[str], after: list[str]) -> list[str]:
    return [
        line for line in difflib.unified_diff(before, after, lineterm="")
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    ]


def _measure_census(census: dict) -> dict[str, int]:
    atomref_counts = census["atomref"]["count"]
    renderlist_keys = census["renderlist"]["keys"]
    page_bearing_diffs = census["page_bearing"]["diff"]
    return {
        "atomref_gap": atomref_counts[1] - atomref_counts[0],
        "renderlist_first_appearance_after_pass2": len(
            sorted(set(renderlist_keys[2]) - set(renderlist_keys[1]))
        ),
        "page_bearing_diff_pass2_to_pass3": len(page_bearing_diffs[1]),
    }


def _load_census_baseline() -> dict[str, dict[str, int]]:
    baseline = PROJECT_ROOT / ".claude" / "baseline-sizes.json"
    try:
        data = json.loads(baseline.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    census = data.get("census", {})
    return census if isinstance(census, dict) else {}


def _write_census_json(fix: "Fixture", census: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _census_output_path(fix.name)
    out_path.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def _prepare_fixture_workspace(fix: "Fixture", tmp_path: Path) -> None:
    local_lvt = tmp_path / f"{fix.name}.tex"
    shutil.copy(fix.path, local_lvt)
    content = local_lvt.read_text(encoding="utf-8")
    local_lvt.write_text(INJECT_L3BUILD_NOOPS + content, encoding="utf-8")
    shutil.copy(STY_FILE, tmp_path / "codependent.sty")
    if RENDER_STY_FILE.exists():
        shutil.copy(RENDER_STY_FILE, tmp_path / "codependent-render.sty")
    if LTXML_FILE.exists():
        shutil.copy(LTXML_FILE, tmp_path / "codependent.ltxml")


def _copy_project_style_files(target_root: Path) -> None:
    """Copy package files needed by isolated fixture compiles."""
    shutil.copy(STY_FILE, target_root / "codependent.sty")
    if RENDER_STY_FILE.exists():
        shutil.copy(RENDER_STY_FILE, target_root / "codependent-render.sty")
    if LTXML_FILE.exists():
        shutil.copy(LTXML_FILE, target_root / "codependent.ltxml")


def _prepare_stress_workspace(fix: "Fixture", tmp_path: Path) -> Path:
    """Create a temp tree that preserves compiled-examples/.latexmkrc paths."""
    compiled_dir = tmp_path / "testfiles" / "compiled-examples"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fix.path, compiled_dir / fix.path.name)
    shutil.copy(COMPILED_EXAMPLES_DIR / ".latexmkrc", compiled_dir / ".latexmkrc")
    support_src = TESTFILES_DIR / "support"
    if support_src.exists():
        shutil.copytree(support_src, tmp_path / "testfiles" / "support")
    _copy_project_style_files(tmp_path)
    return compiled_dir


def _copy_stress_artifacts_to_assertion_root(fix: "Fixture", tmp_path: Path) -> None:
    """Expose latexmk's aux/pdf outputs at the paths _run_assertions expects."""
    artifact_sources = {
        ".aux": tmp_path / "texbuild" / f"{fix.name}.aux",
        ".cdp": tmp_path / "texbuild" / f"{fix.name}.cdp",
        ".log": tmp_path / "texbuild" / f"{fix.name}.log",
        ".pdf": tmp_path / "pdf-out" / f"{fix.name}.pdf",
    }
    for suffix, source in artifact_sources.items():
        if source.exists():
            shutil.copy(source, tmp_path / f"{fix.name}{suffix}")


def _run_census(
    fix: "Fixture",
    engine_bin: Path,
    verbose: bool,
) -> tuple[dict | None, str | None]:
    with tempfile.TemporaryDirectory(prefix=f"codep-census-{fix.name}-") as tmp:
        tmp_path = Path(tmp)
        _prepare_fixture_workspace(fix, tmp_path)
        cmd = [str(engine_bin), "-interaction=nonstopmode"]
        if not fix.expect_package_error:
            cmd.append("-halt-on-error")
        cmd.append(f"{fix.name}.tex")

        atomref_keys_by_pass: list[list[str]] = []
        renderlist_keys_by_pass: list[list[str]] = []
        page_bearing_lines_by_pass: list[list[str]] = []

        for pass_num in range(1, 4):
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                return None, f"census pass {pass_num}: TIMEOUT after 120s"
            if verbose:
                sys.stderr.write(
                    f"  [census] {fix.name} pass {pass_num}: exit {proc.returncode}\n"
                )
            if proc.returncode != 0:
                return None, (
                    f"census pass {pass_num}: exit {proc.returncode} "
                    f"(expected 0 for census compile)"
                )
            aux_path = tmp_path / f"{fix.name}.aux"
            aux_text = aux_path.read_text(encoding="utf-8", errors="replace") if aux_path.exists() else ""
            atomref_keys_by_pass.append(_extract_atomref_keys(aux_text))
            renderlist_keys_by_pass.append(_extract_renderlist_keys(aux_text))
            page_bearing_lines_by_pass.append(_extract_page_bearing_lines(aux_text))

        page_bearing_diffs = [
            _page_bearing_diff(page_bearing_lines_by_pass[0], page_bearing_lines_by_pass[1]),
            _page_bearing_diff(page_bearing_lines_by_pass[1], page_bearing_lines_by_pass[2]),
        ]

        census = {
            "passes": 3,
            "atomref": {
                "count": [len(keys) for keys in atomref_keys_by_pass],
                "keys": atomref_keys_by_pass,
            },
            "renderlist": {
                "count": [len(keys) for keys in renderlist_keys_by_pass],
                "keys": renderlist_keys_by_pass,
            },
            "page_bearing": {
                "count": [len(lines) for lines in page_bearing_lines_by_pass],
                "lines": page_bearing_lines_by_pass,
                "diff": page_bearing_diffs,
                "diff_count": [len(diff) for diff in page_bearing_diffs],
            },
        }
        census["measures"] = _measure_census(census)
        return census, None


def _check_census_assertions(
    fix: "Fixture",
    result: "TestResult",
    census: dict,
    prefix: str = "",
) -> None:
    baseline = _load_census_baseline()
    fixture_baseline = baseline.get(fix.name)
    if not isinstance(fixture_baseline, dict):
        result.failures.append(
            f"{prefix}census baseline missing for {fix.name} in .claude/baseline-sizes.json"
        )
        return

    measures = census.get("measures", {})
    for key in CENSUS_MEASURE_KEYS:
        expected = fixture_baseline.get(key)
        actual = measures.get(key)
        if expected is None:
            result.failures.append(
                f"{prefix}census baseline for {fix.name} missing key {key}"
            )
            continue
        if actual is None:
            result.failures.append(
                f"{prefix}census output for {fix.name} missing key {key}"
            )
            continue
        if actual > expected:
            result.failures.append(
                f"{prefix}census regression {key}: expected <= {expected}, got {actual}"
            )


# ----------------------------------------------------------------------
# Run a single fixture — helpers
# ----------------------------------------------------------------------


def _effective_pass_count(fix: "Fixture", phase: str) -> int:
    """Return compile pass count for `phase` based on fixture declarations."""
    if phase == "cold":
        n = (fix.pass_count_cold
             or fix.phase_assertions.get("cold", {}).get("stable_at")
             or fix.stable_at)
        return n if n > 0 else fix.rerun
    elif phase == "warm":
        n = (fix.pass_count_warm
             or fix.phase_assertions.get("warm", {}).get("stable_at")
             or fix.stable_at)
        return n if n > 0 else 1
    else:  # warm_changed
        n = (fix.pass_count_warm_changed
             or fix.phase_assertions.get("warm_changed", {}).get("stable_at")
             or fix.stable_at)
        return n if n > 0 else fix.rerun


def _effective_fix(fix: "Fixture", phase: str | None) -> "Fixture":
    """Return a copy of fix with phase_assertions[phase] merged into assertion lists."""
    if phase is None:
        return fix
    pa = fix.phase_assertions.get(phase, {})
    if not pa:
        return fix
    copy = dataclasses.replace(fix)
    for field_name, values in pa.items():
        if field_name == "stable_at":
            continue  # consumed by _effective_pass_count, not a runtime assertion
        existing = getattr(copy, field_name, None)
        if isinstance(existing, list):
            merged = list(existing)
            merged.extend(values if isinstance(values, list) else [values])
            setattr(copy, field_name, merged)
    return copy


def _is_multi_phase(fix: "Fixture") -> bool:
    return (
        fix.pass_count_cold > 0
        or fix.pass_count_warm > 0
        or fix.pass_count_warm_changed > 0
        or bool(fix.phase_assertions)
        or bool(fix.warm_mutation)
    )


def _run_phase_compiles(
    fix: "Fixture",
    result: "TestResult",
    engine_bin: Path,
    tmp_path: Path,
    verbose: bool,
    phase: str,
    n: int,
) -> int:
    """Compile `n` passes for `phase`. Appends timeout failures to result. Returns last exit code."""
    last_exit = 0
    cmd_base = [str(engine_bin), "-interaction=nonstopmode"]
    if not fix.expect_package_error:
        cmd_base.append("-halt-on-error")
    for pass_num in range(1, n + 1):
        try:
            proc = subprocess.run(
                cmd_base + [f"{fix.name}.tex"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            last_exit = proc.returncode
            if verbose:
                sys.stderr.write(f"  [{phase}] pass {pass_num}: exit {last_exit}\n")
        except subprocess.TimeoutExpired:
            result.failures.append(f"[{phase}] pass {pass_num}: TIMEOUT after 120s")
            return -1
    return last_exit


def _check_convergence(
    engine_bin: Path,
    fix: "Fixture",
    tmp_path: Path,
    verbose: bool,
    phase: str,
    n: int,
) -> list:
    """Run one extra compile pass; compare .aux before/after. Returns failure list."""
    aux_path = tmp_path / f"{fix.name}.aux"
    aux_before = aux_path.read_text(encoding="utf-8", errors="replace") if aux_path.exists() else ""
    cmd_base = [str(engine_bin), "-interaction=nonstopmode"]
    if not fix.expect_package_error:
        cmd_base.append("-halt-on-error")
    try:
        proc = subprocess.run(
            cmd_base + [f"{fix.name}.tex"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if verbose:
            sys.stderr.write(f"  [{phase}] convergence pass: exit {proc.returncode}\n")
    except subprocess.TimeoutExpired:
        return [f"[{phase}] convergence pass: TIMEOUT after 120s"]
    aux_after = aux_path.read_text(encoding="utf-8", errors="replace") if aux_path.exists() else ""
    if aux_before != aux_after:
        return [
            f"[{phase}] convergence: .aux changed after pass {n + 1} "
            f"(document not stable at {n} passes)"
        ]
    return []


# ----------------------------------------------------------------------
# PDF y-coordinate and dest-page assertion helpers (B-API-TEST-RUNNER-PDF-Y)
# ----------------------------------------------------------------------


def _parse_link_y_near_spec(spec: str) -> "tuple[str, str, float] | None":
    """Parse 'source-text | anchor-text | within=Δpt' for TEST-PDF-LINK-Y-NEAR."""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 3 or not parts[2].startswith("within="):
        return None
    try:
        delta = float(parts[2][7:])
    except ValueError:
        return None
    return parts[0], parts[1], delta


def _parse_link_y_between_spec(spec: str) -> "tuple[str, str, str] | None":
    """Parse 'source-text | top-text | bottom-text' for TEST-PDF-LINK-Y-BETWEEN."""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _parse_dest_page_spec(spec: str) -> "tuple[str, str] | None":
    """Parse 'dest-name | anchor-text' for TEST-PDF-DEST-PAGE."""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _check_pdf_link_y_near(
    link_data: "PdfLinkObjects",
    stext_xml: str,
    spec: str,
    fail,
) -> None:
    """Handle TEST-PDF-LINK-Y-NEAR: <source-text> | <anchor-text> | within=<Δpt>."""
    parsed = _parse_link_y_near_spec(spec)
    if parsed is None:
        fail(
            f"malformed TEST-PDF-LINK-Y-NEAR: {spec!r} "
            "(expected: '<source-text> | <anchor-text> | within=<Δpt>')"
        )
        return
    source_text, anchor_text, within_pt = parsed

    link = _find_link_for_source_text(link_data, stext_xml, source_text)
    if link is None:
        fail(f"TEST-PDF-LINK-Y-NEAR: no link found with source text matching {source_text!r}")
        return
    if not link.dest:
        fail(f"TEST-PDF-LINK-Y-NEAR: link matching {source_text!r} has no named destination")
        return
    dest_info = link_data.dest_data.get(link.dest)
    if dest_info is None:
        fail(f"TEST-PDF-LINK-Y-NEAR: destination {link.dest!r} not found in named destinations")
        return
    if dest_info.y_pdf is None:
        fail(
            f"TEST-PDF-LINK-Y-NEAR: destination {link.dest!r} has no extractable y-coordinate "
            f"(non-XYZ/FitH destination type)"
        )
        return

    dest_page_idx = link_data.page_ref_to_index.get(dest_info.page_ref)
    anchor_result = _find_stext_line_for_text(stext_xml, anchor_text)
    if anchor_result is None:
        fail(f"TEST-PDF-LINK-Y-NEAR: anchor text {anchor_text!r} not found in stext")
        return
    anchor_bbox, anchor_page_height, anchor_page_idx = anchor_result

    if dest_page_idx is not None and anchor_page_idx != dest_page_idx:
        fail(
            f"TEST-PDF-LINK-Y-NEAR: destination {link.dest!r} is on page {dest_page_idx} "
            f"but anchor text {anchor_text!r} is on page {anchor_page_idx}"
        )
        return

    anchor_y_pdf = anchor_page_height - anchor_bbox[1]
    delta = abs(dest_info.y_pdf - anchor_y_pdf)
    if delta > within_pt:
        fail(
            f"TEST-PDF-LINK-Y-NEAR: destination {link.dest!r} y={dest_info.y_pdf:.1f} "
            f"is {delta:.1f}pt from anchor {anchor_text!r} y={anchor_y_pdf:.1f} "
            f"(within={within_pt}pt required)"
        )


def _check_pdf_link_y_between(
    link_data: "PdfLinkObjects",
    stext_xml: str,
    spec: str,
    fail,
) -> None:
    """Handle TEST-PDF-LINK-Y-BETWEEN: <source-text> | <top-text> | <bottom-text>."""
    parsed = _parse_link_y_between_spec(spec)
    if parsed is None:
        fail(
            f"malformed TEST-PDF-LINK-Y-BETWEEN: {spec!r} "
            "(expected: '<source-text> | <top-text> | <bottom-text>')"
        )
        return
    source_text, top_text, bottom_text = parsed

    link = _find_link_for_source_text(link_data, stext_xml, source_text)
    if link is None:
        fail(f"TEST-PDF-LINK-Y-BETWEEN: no link found with source text matching {source_text!r}")
        return
    if not link.dest:
        fail(f"TEST-PDF-LINK-Y-BETWEEN: link matching {source_text!r} has no named destination")
        return
    dest_info = link_data.dest_data.get(link.dest)
    if dest_info is None:
        fail(f"TEST-PDF-LINK-Y-BETWEEN: destination {link.dest!r} not found in named dests")
        return
    if dest_info.y_pdf is None:
        fail(
            f"TEST-PDF-LINK-Y-BETWEEN: destination {link.dest!r} has no extractable y-coordinate"
        )
        return

    top_result = _find_stext_line_for_text(stext_xml, top_text)
    if top_result is None:
        fail(f"TEST-PDF-LINK-Y-BETWEEN: top-text {top_text!r} not found in stext")
        return
    top_bbox, top_page_height, top_page_idx = top_result

    bottom_result = _find_stext_line_for_text(stext_xml, bottom_text)
    if bottom_result is None:
        fail(f"TEST-PDF-LINK-Y-BETWEEN: bottom-text {bottom_text!r} not found in stext")
        return
    bottom_bbox, bottom_page_height, bottom_page_idx = bottom_result

    if top_page_idx != bottom_page_idx:
        fail("TEST-PDF-LINK-Y-BETWEEN: top-text and bottom-text are on different pages")
        return
    dest_page_idx = link_data.page_ref_to_index.get(dest_info.page_ref)
    if dest_page_idx is not None and dest_page_idx != top_page_idx:
        fail(
            f"TEST-PDF-LINK-Y-BETWEEN: destination {link.dest!r} is on page {dest_page_idx} "
            f"but reference texts are on page {top_page_idx}"
        )
        return

    # Convert to PDF bottom-up coords; "top" text (higher on page) → larger PDF y.
    top_y_pdf = top_page_height - top_bbox[1]
    bottom_y_pdf = bottom_page_height - bottom_bbox[1]
    dest_y = dest_info.y_pdf

    if not (bottom_y_pdf < dest_y < top_y_pdf):
        fail(
            f"TEST-PDF-LINK-Y-BETWEEN: destination {link.dest!r} y={dest_y:.1f} "
            f"not strictly between top={top_y_pdf:.1f} ({top_text!r}) "
            f"and bottom={bottom_y_pdf:.1f} ({bottom_text!r})"
        )


def _check_pdf_dest_page(
    link_data: "PdfLinkObjects",
    stext_xml: str,
    spec: str,
    fail,
) -> None:
    """Handle TEST-PDF-DEST-PAGE: <dest-name> | <anchor-text>."""
    parsed = _parse_dest_page_spec(spec)
    if parsed is None:
        fail(
            f"malformed TEST-PDF-DEST-PAGE: {spec!r} "
            "(expected: '<dest-name> | <anchor-text>')"
        )
        return
    dest_name, anchor_text = parsed

    matched_key = next(
        (k for k in link_data.dest_data if re.search(dest_name, k)), None
    )
    dest_info = link_data.dest_data.get(matched_key) if matched_key else None
    if dest_info is None:
        sample = sorted(link_data.dest_data.keys())[:8]
        fail(
            f"TEST-PDF-DEST-PAGE: named destination {dest_name!r} not found "
            f"(known dests: {sample})"
        )
        return
    dest_page_idx = link_data.page_ref_to_index.get(dest_info.page_ref)
    if dest_page_idx is None:
        fail(
            f"TEST-PDF-DEST-PAGE: destination {dest_name!r} page_ref={dest_info.page_ref!r} "
            f"not resolvable in page tree"
        )
        return

    anchor_result = _find_stext_line_for_text(stext_xml, anchor_text)
    if anchor_result is None:
        fail(f"TEST-PDF-DEST-PAGE: anchor text {anchor_text!r} not found in stext")
        return
    _, _anchor_ph, anchor_page_idx = anchor_result

    if dest_page_idx != anchor_page_idx:
        fail(
            f"TEST-PDF-DEST-PAGE: destination {dest_name!r} is on page {dest_page_idx} "
            f"but anchor text {anchor_text!r} is on page {anchor_page_idx}"
        )


def _run_assertions(
    fix: "Fixture",
    result: "TestResult",
    tmp_path: Path,
    last_exit: int,
    prefix: str = "",
) -> None:
    """Evaluate fix's assertions against current artifacts in tmp_path."""
    log_file = tmp_path / f"{fix.name}.log"
    aux_file = tmp_path / f"{fix.name}.aux"
    cdp_file = tmp_path / f"{fix.name}.cdp"

    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    aux_text = aux_file.read_text(encoding="utf-8", errors="replace") if aux_file.exists() else ""
    cdp_text = cdp_file.read_text(encoding="utf-8", errors="replace") if cdp_file.exists() else ""

    def fail(msg: str) -> None:
        result.failures.append(f"{prefix}{msg}")

    # 1. Exit code.
    if last_exit != fix.exit_code:
        fail(f"exit code: expected {fix.exit_code}, got {last_exit}")
        tail = log_text.splitlines()[-30:]
        result.log_excerpt = "\n".join(tail)

    # 2. log_not patterns.
    for pat in fix.log_not:
        if re.search(pat, log_text):
            fail(f"log matched forbidden pattern: {pat}")

    # 3. log_contains patterns.
    for pat in fix.log_contains:
        if not re.search(pat, log_text):
            fail(f"log missing required pattern: {pat}")

    # 3a. Universal undefined-ref hygiene.
    if not fix.allow_undefined_refs:
        if re.search(r"There were undefined references\.", log_text):
            fail(
                "undefined references in log "
                "(set TEST-ALLOW-UNDEFINED-REFS: yes if intentional)"
            )
        if re.search(
            r"cref reference format for label type `[^']+' undefined",
            log_text,
        ):
            fail(
                "cleveref type undefined — missing \\crefname for some label type"
            )

    # 4. CDP assertions.
    for s in fix.cdp_contains:
        if s not in cdp_text:
            fail(f"cdp missing required string: {s}")
    for s in fix.cdp_not_contains:
        if s in cdp_text:
            fail(f"cdp contains forbidden string: {s}")

    # 5. CDP counts: format "<pattern> = <n>".
    for spec in fix.cdp_count:
        try:
            pat, expected = spec.rsplit("=", 1)
            pat = pat.strip()
            expected_n = int(expected.strip())
        except ValueError:
            fail(f"malformed TEST-CDP-COUNT: {spec}")
            continue
        actual = cdp_text.count(pat)
        if actual != expected_n:
            fail(f"cdp count for {pat!r}: expected {expected_n}, got {actual}")

    # 6. AUX assertions.
    for s in fix.aux_contains:
        if s not in aux_text:
            fail(f"aux missing required string: {s}")
    for s in fix.aux_not_contains:
        if s in aux_text:
            fail(f"aux contains forbidden string: {s}")

    # 7. atoms_min: count \codep@cdp@atom records.
    if fix.atoms_min > 0:
        atom_count = cdp_text.count("\\codep@cdp@atom{")
        if atom_count < fix.atoms_min:
            fail(f"atom count: expected >= {fix.atoms_min}, got {atom_count}")

    # 8. cdp_last_record: last NON-EMPTY line of .cdp must contain this string.
    if fix.cdp_last_record:
        non_empty_lines = [ln for ln in cdp_text.splitlines() if ln.strip()]
        if not non_empty_lines:
            fail(f"cdp last-record check: file is empty, expected {fix.cdp_last_record!r}")
        elif fix.cdp_last_record not in non_empty_lines[-1]:
            fail(
                f"cdp last-record: expected {fix.cdp_last_record!r}, "
                f"got last non-empty line: {non_empty_lines[-1]!r}"
            )

    # 9. PDF content assertions.
    has_pdf_checks = (
        fix.pdf_contains or fix.pdf_not or fix.pdf_links > 0
        or fix.pdf_stext or fix.pdf_stext_not
        or fix.pdf_objects or fix.pdf_objects_not
        or fix.pdf_link_dest or fix.pdf_link_dest_not
        or fix.pdf_link_count >= 0
        or fix.pdf_dest_exists or fix.pdf_dest_not_exists
        or fix.pdf_link_rect or fix.pdf_no_orphan_links
        or fix.pdf_all_backrefs_linked or fix.pdf_backref_targets
        or fix.pdf_backref_sources_rendered
        or fix.pdf_vspace_between
        or fix.pdf_pages >= 0
    )
    if has_pdf_checks:
        pdf_file = tmp_path / f"{fix.name}.pdf"
        if not pdf_file.exists():
            fail("pdf assertions present but no PDF was produced")
        elif PDF_TEXT_TOOL is None and (fix.pdf_contains or fix.pdf_not):
            fail(
                "PDF text assertions require mutool or pdftotext "
                "(not on PATH). Run inside 'nix develop'."
            )
        else:
            if fix.pdf_contains or fix.pdf_not:
                pdf_text = _extract_pdf_text(pdf_file)
                if pdf_text is None:
                    fail(f"pdf text extraction failed (tool: {PDF_TEXT_TOOL})")
                else:
                    for s in fix.pdf_contains:
                        if s not in pdf_text:
                            fail(f"pdf missing required text: {s!r}")
                    for s in fix.pdf_not:
                        if s in pdf_text:
                            fail(f"pdf contains forbidden text: {s!r}")

            if not fix.allow_undefined_refs:
                if PDF_TEXT_TOOL is None:
                    fail(
                        "undefined-ref PDF check requires mutool or pdftotext "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    pdf_text = locals().get("pdf_text")
                    if pdf_text is None:
                        pdf_text = _extract_pdf_text(pdf_file)
                    if pdf_text is None:
                        fail(f"pdf text extraction failed (tool: {PDF_TEXT_TOOL})")
                    elif re.search(r"(?<![0-9])\?\?(?![0-9])", pdf_text):
                        fail("?? token in PDF output (undefined ref rendered)")

            if fix.pdf_links > 0:
                if PDF_LINK_TOOL is None:
                    fail(
                        "PDF link count assertion requires mutool or qpdf "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    link_count = _count_pdf_links(pdf_file)
                    if link_count is None:
                        fail(f"pdf link counting failed (tool: {PDF_LINK_TOOL})")
                    elif link_count < fix.pdf_links:
                        fail(f"pdf links: expected >= {fix.pdf_links}, got {link_count}")

            if fix.pdf_pages >= 0:
                if PDF_QPDF_TOOL is None:
                    fail(
                        "TEST-PDF-PAGES requires qpdf "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    page_count = _count_pdf_pages(pdf_file)
                    if page_count is None:
                        fail(f"pdf page counting failed (tool: {PDF_QPDF_TOOL})")
                    elif page_count != fix.pdf_pages:
                        fail(
                            f"pdf pages: expected {fix.pdf_pages}, got {page_count}"
                        )

            # 10. Structured text assertions.
            if fix.pdf_stext or fix.pdf_stext_not or fix.pdf_vspace_between:
                if PDF_STEXT_TOOL is None:
                    fail(
                        "PDF stext assertions require mutool "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    stext_xml = _extract_pdf_stext(pdf_file)
                    if stext_xml is None:
                        fail("pdf stext extraction failed")
                    else:
                        for pat in fix.pdf_stext:
                            if not re.search(pat, stext_xml):
                                fail(f"pdf stext missing pattern: {pat!r}")
                        for pat in fix.pdf_stext_not:
                            if re.search(pat, stext_xml):
                                fail(f"pdf stext matched forbidden pattern: {pat!r}")
                        for spec in fix.pdf_vspace_between:
                            parsed = _parse_pdf_vspace_between_spec(spec)
                            if parsed is None:
                                fail(
                                    f"malformed TEST-PDF-VSPACE-BETWEEN: {spec!r} "
                                    "(expected: '<anchor1-regex> <anchor2-regex> <max-points>' "
                                    "with shell-style quoting for spaces)"
                                )
                                continue
                            anchor1_regex, anchor2_regex, max_points = parsed
                            gap, err = _measure_pdf_vspace_between(
                                stext_xml, anchor1_regex, anchor2_regex
                            )
                            if err is not None:
                                fail(f"TEST-PDF-VSPACE-BETWEEN: {err}")
                            elif gap is not None and gap > max_points:
                                fail(
                                    "TEST-PDF-VSPACE-BETWEEN: "
                                    f"gap {gap:.2f}pt exceeds max {max_points:.2f}pt "
                                    f"between {anchor1_regex!r} and {anchor2_regex!r}"
                                )

            # 11. PDF object assertions.
            if fix.pdf_objects or fix.pdf_objects_not:
                if PDF_STEXT_TOOL is None:
                    sys.stderr.write(
                        f"  WARN: skipping PDF object checks for {fix.name} "
                        f"(no mutool on PATH)\n"
                    )
                else:
                    obj_dump = _extract_pdf_objects(pdf_file)
                    if obj_dump is None:
                        fail("pdf object extraction failed")
                    else:
                        for pat in fix.pdf_objects:
                            if not re.search(pat, obj_dump):
                                fail(f"pdf objects missing pattern: {pat!r}")
                        for pat in fix.pdf_objects_not:
                            if re.search(pat, obj_dump):
                                fail(f"pdf objects matched forbidden pattern: {pat!r}")

            # 12. Object-level PDF link verification (qpdf --json=2).
            has_qpdf_checks = (
                fix.pdf_link_dest or fix.pdf_link_dest_not
                or fix.pdf_link_count >= 0
                or fix.pdf_dest_exists or fix.pdf_dest_not_exists
                or fix.pdf_link_rect or fix.pdf_no_orphan_links
            )
            if has_qpdf_checks:
                if PDF_QPDF_TOOL is None:
                    fail(
                        "PDF link/dest assertions require qpdf "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    link_data = _extract_pdf_link_objects(pdf_file)
                    if link_data is None:
                        fail(f"pdf link object extraction failed (tool: {PDF_QPDF_TOOL})")
                    else:
                        for pat in fix.pdf_link_dest:
                            if not any(re.search(pat, lnk.dest) for lnk in link_data.links):
                                fail(f"pdf link dest missing pattern: {pat!r}")
                        for pat in fix.pdf_link_dest_not:
                            for lnk in link_data.links:
                                if re.search(pat, lnk.dest):
                                    fail(
                                        f"pdf link dest matched forbidden "
                                        f"pattern: {pat!r} (on {lnk.dest!r})"
                                    )
                                    break
                        if fix.pdf_link_count >= 0:
                            actual = len(link_data.links)
                            if actual != fix.pdf_link_count:
                                fail(
                                    f"pdf link count: expected "
                                    f"{fix.pdf_link_count}, got {actual}"
                                )
                        for pat in fix.pdf_dest_exists:
                            if not any(re.search(pat, d) for d in link_data.destinations):
                                fail(f"pdf named dest missing pattern: {pat!r}")
                        for pat in fix.pdf_dest_not_exists:
                            for d in link_data.destinations:
                                if re.search(pat, d):
                                    fail(
                                        f"pdf named dest matched forbidden "
                                        f"pattern: {pat!r} (on {d!r})"
                                    )
                                    break
                        for spec in fix.pdf_link_rect:
                            parts = spec.split()
                            if len(parts) != 6:
                                fail(f"malformed TEST-PDF-LINK-RECT: {spec}")
                                continue
                            dest_pat = parts[0]
                            try:
                                ex = [float(x) for x in parts[1:5]]
                                tol = float(parts[5])
                            except ValueError:
                                fail(f"malformed TEST-PDF-LINK-RECT coords: {spec}")
                                continue
                            matched = False
                            for lnk in link_data.links:
                                if not re.search(dest_pat, lnk.dest):
                                    continue
                                if len(lnk.rect) == 4:
                                    diffs = [abs(lnk.rect[i] - ex[i]) for i in range(4)]
                                    if all(d <= tol for d in diffs):
                                        matched = True
                                        break
                            if not matched:
                                fail(
                                    f"pdf link rect: no link matching "
                                    f"dest={dest_pat!r} with rect ~{ex} (tol={tol})"
                                )
                        if fix.pdf_no_orphan_links:
                            orphans = [
                                lnk.dest for lnk in link_data.links
                                if lnk.dest and lnk.dest not in link_data.destinations
                            ]
                            if orphans:
                                unique = sorted(set(orphans))
                                fail(
                                    f"pdf orphan links ({len(orphans)}): "
                                    f"dests not in Names tree: "
                                    f"{', '.join(unique[:10])}"
                                )

            # 13. Backref hyperlink verification.
            has_backref_checks = (
                fix.pdf_all_backrefs_linked
                or fix.pdf_backref_targets
                or fix.pdf_backref_entry_targets
                or fix.pdf_backref_sources_rendered
            )
            if has_backref_checks:
                if PDF_STEXT_TOOL is None or PDF_QPDF_TOOL is None:
                    missing = [
                        t for t, v in [("mutool", PDF_STEXT_TOOL), ("qpdf", PDF_QPDF_TOOL)]
                        if v is None
                    ]
                    fail(
                        f"PDF backref assertions require mutool and qpdf "
                        f"(missing: {', '.join(missing)}). "
                        f"Run inside 'nix develop'."
                    )
                else:
                    stext_xml = _extract_pdf_stext(pdf_file)
                    if stext_xml is None:
                        fail("backref check: stext extraction failed")
                    else:
                        backref_lines = _parse_backref_lines_from_stext(stext_xml)
                        br_link_data = _extract_pdf_link_objects(pdf_file)
                        if br_link_data is None:
                            fail("backref check: qpdf extraction failed")
                        else:
                            if fix.pdf_all_backrefs_linked:
                                if not backref_lines:
                                    fail("all-backrefs-linked: no 'Used in' lines found in PDF")
                                for bline in backref_lines:
                                    overlapping = _links_overlapping_line(br_link_data, bline)
                                    n_entries = len(bline.entries)
                                    n_links = len(overlapping)
                                    if n_links < n_entries:
                                        fail(
                                            f"all-backrefs-linked: '{bline.text}' has "
                                            f"{n_entries} entries but only {n_links} covering link(s)"
                                        )
                                    for link in overlapping:
                                        if (
                                            link.dest
                                            and link.dest not in br_link_data.destinations
                                        ):
                                            fail(
                                                f"all-backrefs-linked: '{bline.text}' has link "
                                                f"with dest '{link.dest}' that does not exist "
                                                f"in PDF named destinations"
                                            )
                            # LHS atom_pat is currently ignored; use TEST-PDF-BACKREF-ENTRY-TARGET for strict entry-level checks.
                            for spec in fix.pdf_backref_targets:
                                if "=" not in spec:
                                    fail(f"malformed TEST-PDF-BACKREF-TARGETS: {spec}")
                                    continue
                                atom_pat, targets_str = spec.split("=", 1)
                                atom_pat = atom_pat.strip()
                                expected_dests = [
                                    d.strip() for d in targets_str.split(",") if d.strip()
                                ]
                                matched_line = None
                                for bline in backref_lines:
                                    overlapping = _links_overlapping_line(br_link_data, bline)
                                    link_dests = [lnk.dest for lnk in overlapping]
                                    if all(
                                        any(re.search(dp, ld) for ld in link_dests)
                                        for dp in expected_dests
                                    ):
                                        matched_line = bline
                                        break
                                if matched_line is None:
                                    summaries = []
                                    for bline in backref_lines[:5]:
                                        ov = _links_overlapping_line(br_link_data, bline)
                                        summaries.append(
                                            f"'{bline.text}' -> {[l.dest for l in ov][:4]}"
                                        )
                                    fail(
                                        f"backref-targets: no 'Used in' line found with links "
                                        f"matching all of {expected_dests} "
                                        f"(atom pattern: {atom_pat!r}). "
                                        f"Lines found: {'; '.join(summaries)}"
                                    )
                            for spec in fix.pdf_backref_entry_targets:
                                # Parse: "<atom_pat> | <entry_text> = <dest_pat>"
                                if "=" not in spec or "|" not in spec:
                                    fail(f"malformed TEST-PDF-BACKREF-ENTRY-TARGET: {spec}")
                                    continue
                                lhs, dest_pat = spec.split("=", 1)
                                dest_pat = dest_pat.strip()
                                lhs_parts = lhs.split("|", 1)
                                if len(lhs_parts) != 2:
                                    fail(f"malformed TEST-PDF-BACKREF-ENTRY-TARGET: {spec}")
                                    continue
                                atom_pat = lhs_parts[0].strip()
                                entry_text = lhs_parts[1].strip()
                                # Step 1: bind rows whose link destinations include atom_pat.
                                candidate_rows = []
                                all_atom_dests = []
                                for bline in backref_lines:
                                    overlapping = _links_overlapping_line(br_link_data, bline)
                                    row_dests = [lnk.dest for lnk in overlapping if lnk.dest]
                                    all_atom_dests.extend(row_dests)
                                    if any(re.search(atom_pat, d) for d in row_dests):
                                        candidate_rows.append(bline)
                                if not candidate_rows:
                                    fail(
                                        f"backref-entry-target: no 'Used in' row found whose "
                                        f"link destinations match atom_pat={atom_pat!r}. "
                                        f"Candidate atom dests seen: "
                                        f"{sorted(set(all_atom_dests))[:10]}"
                                    )
                                    continue
                                # Step 2: within candidate rows, find entry_text and check dest.
                                spec_passed = False
                                entry_errors = []
                                for bline in candidate_rows:
                                    if entry_text not in bline.text:
                                        entry_errors.append(
                                            f"row '{bline.text}' does not contain entry_text={entry_text!r}"
                                        )
                                        continue
                                    # Find x-range of entry_text within the row.
                                    xrange = _x_range_of_entry_text(bline, entry_text)
                                    if xrange is None:
                                        entry_errors.append(
                                            f"row '{bline.text}': could not determine "
                                            f"x-range for entry_text={entry_text!r} "
                                            f"(no char data or entry not locatable)"
                                        )
                                        continue
                                    entry_x_left, entry_x_right = xrange
                                    # Find links covering that x-range on this line.
                                    entry_links = _find_link_for_entry(
                                        br_link_data, bline, entry_x_left, entry_x_right
                                    )
                                    if not entry_links:
                                        entry_errors.append(
                                            f"row '{bline.text}': no link found "
                                            f"covering x=[{entry_x_left:.1f},{entry_x_right:.1f}] "
                                            f"for entry_text={entry_text!r}"
                                        )
                                        continue
                                    # Check dest_pat against each candidate link.
                                    matching_dests = [
                                        lnk.dest for lnk in entry_links
                                        if lnk.dest and re.search(dest_pat, lnk.dest)
                                    ]
                                    if matching_dests:
                                        spec_passed = True
                                        break
                                    actual_dests = [lnk.dest for lnk in entry_links]
                                    entry_errors.append(
                                        f"row '{bline.text}': entry_text={entry_text!r} "
                                        f"has link(s) with dest(s) {actual_dests} "
                                        f"— none match dest_pat={dest_pat!r}"
                                    )
                                if not spec_passed:
                                    fail(
                                        f"backref-entry-target: "
                                        f"atom_pat={atom_pat!r} entry_text={entry_text!r} "
                                        f"dest_pat={dest_pat!r} — not satisfied. "
                                        f"Details: {'; '.join(entry_errors)}"
                                    )
                            if fix.pdf_backref_sources_rendered:
                                _check_backref_sources_rendered(
                                    backref_lines, stext_xml, fail
                                )

    # 14. Package warning assertions.
    for pat in fix.expect_package_warning:
        if not re.search(rf"Package codependent Warning:.*?{pat}", log_text, re.DOTALL):
            fail(f"expected package warning matching {pat!r} not found in log")

    # 15. Package error assertions.
    for pat in fix.expect_package_error:
        if not re.search(rf"Package codependent Error:.*?{pat}", log_text, re.DOTALL):
            fail(f"expected package error matching {pat!r} not found in log")

    # 16. Appendix entry assertions.
    has_appendix_checks = fix.pdf_appendix_entry or fix.pdf_appendix_entry_text_only
    if has_appendix_checks:
        appendix_specs = fix.pdf_appendix_entry or fix.pdf_appendix_entry_text_only
        need_dest_check = bool(fix.pdf_appendix_entry)
        pdf_file = tmp_path / f"{fix.name}.pdf"
        if not pdf_file.exists():
            fail("appendix assertions present but no PDF was produced")
        else:
            link_data = None
            if need_dest_check:
                if PDF_QPDF_TOOL is None:
                    fail(
                        "TEST-PDF-APPENDIX-ENTRY requires qpdf "
                        "(not on PATH). Run inside 'nix develop'."
                    )
                else:
                    link_data = _extract_pdf_link_objects(pdf_file)
                    if link_data is None:
                        fail("appendix dest check: qpdf extraction failed")
            stext_xml = None
            if PDF_STEXT_TOOL is None:
                fail(
                    "appendix text assertions require mutool "
                    "(not on PATH). Run inside 'nix develop'."
                )
            else:
                stext_xml = _extract_pdf_stext(pdf_file)
                if stext_xml is None:
                    fail("appendix stext extraction failed")
            for spec in appendix_specs:
                parsed = _parse_appendix_entry_spec(spec)
                if parsed is None:
                    fail(f"malformed appendix entry spec: {spec!r}")
                    continue
                atom_key, display_number, printed_kind = parsed
                dest_name = f"codep-appendix:{atom_key}"
                if need_dest_check and link_data is not None:
                    if dest_name not in link_data.destinations:
                        fail(f"appendix named dest {dest_name!r} not found in PDF")
                if stext_xml is not None:
                    if display_number not in stext_xml:
                        fail(
                            f"appendix entry {atom_key!r}: display number "
                            f"{display_number!r} not found in PDF text"
                        )
                    if printed_kind and printed_kind not in stext_xml:
                        fail(
                            f"appendix entry {atom_key!r}: printed kind "
                            f"{printed_kind!r} not found in PDF text"
                        )
            if not fix.appendix_enum_waiver:
                n_dirs = len(appendix_specs)
                if need_dest_check and link_data is not None:
                    n_entries = _count_appendix_entries_in_pdf(link_data)
                    if n_entries != n_dirs:
                        fail(
                            f"appendix enumeration mismatch: {n_dirs} directive(s) "
                            f"but {n_entries} codep-appendix: destination(s) in PDF "
                            f"(declare TEST-APPENDIX-ENUM-WAIVER to suppress)"
                        )
                # TEXT-ONLY: informational guard — no dest count available yet

    # 17. PDF y-coordinate and dest-page assertions (B-API-TEST-RUNNER-PDF-Y).
    has_y_checks = fix.pdf_link_y_near or fix.pdf_link_y_between or fix.pdf_dest_page
    if has_y_checks:
        pdf_file = tmp_path / f"{fix.name}.pdf"
        if not pdf_file.exists():
            fail("y-coordinate assertions present but no PDF was produced")
        elif PDF_STEXT_TOOL is None or PDF_QPDF_TOOL is None:
            missing = [
                t for t, v in [("mutool", PDF_STEXT_TOOL), ("qpdf", PDF_QPDF_TOOL)]
                if v is None
            ]
            fail(
                f"PDF y-coordinate assertions require mutool and qpdf "
                f"(missing: {', '.join(missing)}). Run inside 'nix develop'."
            )
        else:
            y_stext = _extract_pdf_stext(pdf_file)
            y_link_data = _extract_pdf_link_objects(pdf_file)
            if y_stext is None:
                fail("y-check: stext extraction failed")
            elif y_link_data is None:
                fail(f"y-check: qpdf extraction failed (tool: {PDF_QPDF_TOOL})")
            else:
                for spec in fix.pdf_link_y_near:
                    _check_pdf_link_y_near(y_link_data, y_stext, spec, fail)
                for spec in fix.pdf_link_y_between:
                    _check_pdf_link_y_between(y_link_data, y_stext, spec, fail)
                for spec in fix.pdf_dest_page:
                    _check_pdf_dest_page(y_link_data, y_stext, spec, fail)


# ----------------------------------------------------------------------
# Multi-phase runner
# ----------------------------------------------------------------------


def _run_multi_phase(
    fix: "Fixture",
    result: "TestResult",
    engine_bin: Path,
    tmp_path: Path,
    verbose: bool,
) -> None:
    """Execute COLD, WARM, and (if mutation declared) WARM-CHANGED phases."""

    # COLD: tmp dir starts clean (standard TemporaryDirectory setup)
    cold_n = _effective_pass_count(fix, "cold")
    last_exit = _run_phase_compiles(fix, result, engine_bin, tmp_path, verbose, "cold", cold_n)
    if last_exit >= 0:
        result.failures.extend(
            _check_convergence(engine_bin, fix, tmp_path, verbose, "cold", cold_n)
        )
    _run_assertions(_effective_fix(fix, "cold"), result, tmp_path, last_exit, prefix="[cold] ")

    # WARM: .aux/.cdp intact from COLD
    warm_n = _effective_pass_count(fix, "warm")
    last_exit = _run_phase_compiles(fix, result, engine_bin, tmp_path, verbose, "warm", warm_n)
    if last_exit >= 0:
        result.failures.extend(
            _check_convergence(engine_bin, fix, tmp_path, verbose, "warm", warm_n)
        )
    _run_assertions(_effective_fix(fix, "warm"), result, tmp_path, last_exit, prefix="[warm] ")

    # WARM-CHANGED: apply mutation, recompile, revert
    if not fix.warm_mutation:
        return

    original_content = fix.path.read_text(encoding="utf-8")
    try:
        mut_proc = subprocess.run(
            fix.warm_mutation,
            shell=True,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if mut_proc.returncode != 0:
            result.failures.append(
                f"[warm_changed] mutation command failed "
                f"(exit {mut_proc.returncode}): {fix.warm_mutation!r}"
            )
            return

        # Re-copy mutated source into temp dir (inject noops again)
        mutated = fix.path.read_text(encoding="utf-8")
        (tmp_path / f"{fix.name}.tex").write_text(
            INJECT_L3BUILD_NOOPS + mutated, encoding="utf-8"
        )

        wc_n = _effective_pass_count(fix, "warm_changed")
        last_exit = _run_phase_compiles(
            fix, result, engine_bin, tmp_path, verbose, "warm_changed", wc_n
        )
        if last_exit >= 0:
            result.failures.extend(
                _check_convergence(engine_bin, fix, tmp_path, verbose, "warm_changed", wc_n)
            )
        _run_assertions(
            _effective_fix(fix, "warm_changed"), result, tmp_path, last_exit,
            prefix="[warm_changed] "
        )
    finally:
        fix.path.write_text(original_content, encoding="utf-8")


# ----------------------------------------------------------------------
# Run a single fixture
# ----------------------------------------------------------------------


@dataclasses.dataclass
class TestResult:
    fixture: "Fixture"
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    failures: list = dataclasses.field(default_factory=list)
    duration_ms: int = 0
    log_excerpt: str = ""


def _is_direct_stress_fixture(fix: "Fixture") -> bool:
    return fix.path.suffix == ".tex" and fix.kind == "stress"


def _run_stress_fixture(
    fix: "Fixture",
    result: "TestResult",
    tmp_path: Path,
    verbose: bool,
) -> None:
    """Compile a LIVE stress .tex fixture through latexmk and assert artifacts."""
    latexmk_bin = shutil.which("latexmk")
    if latexmk_bin is None:
        result.failures.append("latexmk not found on PATH; run inside 'nix develop'")
        return

    compiled_dir = _prepare_stress_workspace(fix, tmp_path)
    cmd = [
        latexmk_bin,
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        fix.path.name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=compiled_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        result.failures.append("latexmk stress compile: TIMEOUT after 300s")
        return

    if verbose:
        sys.stderr.write(f"  latexmk stress compile: exit {proc.returncode}\n")
    _copy_stress_artifacts_to_assertion_root(fix, tmp_path)
    if proc.returncode != fix.exit_code:
        log_file = tmp_path / f"{fix.name}.log"
        log_text = (
            log_file.read_text(encoding="utf-8", errors="replace")
            if log_file.exists()
            else ""
        )
        result.log_excerpt = "\n".join(log_text.splitlines()[-30:])
    _run_assertions(fix, result, tmp_path, proc.returncode, prefix="")


def run_fixture(
    fix: "Fixture",
    engine_bin: Path,
    keep_temp: bool,
    verbose: bool,
    force_census: bool = False,
) -> "TestResult":
    """Compile a fixture and verify its assertions."""
    t0 = time.time()
    result = TestResult(fixture=fix, passed=False)

    if fix.parse_error:
        result.failures.append(f"parse error: {fix.parse_error}")
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    if not STY_FILE.exists():
        result.skipped = True
        result.skip_reason = (
            f"codependent.sty not found at {STY_FILE} (implementation not landed yet)"
        )
        return result

    with tempfile.TemporaryDirectory(prefix=f"codep-test-{fix.name}-") as tmp:
        tmp_path = Path(tmp)
        if _is_direct_stress_fixture(fix):
            _run_stress_fixture(fix, result, tmp_path, verbose)
        else:
            _prepare_fixture_workspace(fix, tmp_path)
            if _is_multi_phase(fix):
                _run_multi_phase(fix, result, engine_bin, tmp_path, verbose)
            else:
                # Single-phase: compile `rerun` times then check assertions once.
                run_log = []
                for pass_num in range(1, fix.rerun + 1):
                    cmd = [str(engine_bin), "-interaction=nonstopmode"]
                    if not fix.expect_package_error:
                        cmd.append("-halt-on-error")
                    cmd.append(f"{fix.name}.tex")
                    try:
                        proc = subprocess.run(
                            cmd, cwd=tmp_path, capture_output=True, text=True, timeout=120,
                        )
                    except subprocess.TimeoutExpired:
                        result.failures.append(f"pass {pass_num}: TIMEOUT after 120s")
                        result.duration_ms = int((time.time() - t0) * 1000)
                        return result
                    run_log.append(("pass", pass_num, proc.returncode))
                    if verbose:
                        sys.stderr.write(f"  pass {pass_num}: exit {proc.returncode}\n")

                last_exit = run_log[-1][2] if run_log else -1
                _run_assertions(fix, result, tmp_path, last_exit, prefix="")

        if keep_temp:
            persistent = TESTFILES_DIR / "tmp" / fix.name
            persistent.parent.mkdir(parents=True, exist_ok=True)
            if persistent.exists():
                shutil.rmtree(persistent)
            shutil.copytree(tmp_path, persistent)

    census_requested = force_census or fix.census
    if census_requested:
        census, census_error = _run_census(fix, engine_bin, verbose)
        if census_error is not None:
            result.failures.append(census_error)
        elif census is not None:
            out_path = _write_census_json(fix, census)
            if verbose:
                sys.stderr.write(
                    f"  [census] wrote {out_path} "
                    f"measures={census.get('measures', {})}\n"
                )
            if fix.census_pass:
                _check_census_assertions(fix, result, census)

    result.passed = not result.failures
    result.duration_ms = int((time.time() - t0) * 1000)
    return result


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


DISCOVERY_SKIP_DIRS = {"output", "tmp", "corpus", "__pycache__"}


def _is_active_fixture_path(path: Path, real_world: bool) -> bool:
    parts = set(path.parts)
    if parts & DISCOVERY_SKIP_DIRS:
        return False
    if not real_world and "real-world" in parts:
        return False
    return True


def _matches_filter(path: Path, pattern: str | None) -> bool:
    return pattern is None or re.search(pattern, path.name) is not None


def _parse_fixture_for_discovery(path: Path) -> Fixture | None:
    try:
        return parse_fixture(path)
    except Exception as e:
        sys.stderr.write(f"WARN: failed to parse {path}: {e}\n")
        return None


def _fixture_headers(path: Path) -> dict:
    return parse_test_kind_headers(path).get("headers", {})


def _reject_root_lvt_fixtures() -> None:
    root_lvt = sorted(TESTFILES_DIR.glob("*.lvt"))
    if not root_lvt:
        return
    offenders = "\n  ".join(str(path) for path in root_lvt)
    raise SystemExit(
        "testfiles/ root must not contain .lvt files; only unit/ and integration/\n"
        "Offenders:\n  " + offenders + "\n"
        "Move to testfiles/unit/ or testfiles/integration/, or delete."
    )


def _discover_lvt_fixtures(
    selected_kinds: set[str],
    real_world: bool,
    pattern: str | None,
) -> list[Fixture]:
    fixtures: list[Fixture] = []
    active_dirs = [UNIT_DIR, INTEGRATION_DIR]
    if real_world:
        active_dirs.append(REAL_WORLD_DIR)
    for directory in active_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.lvt")):
            if (
                not _is_active_fixture_path(path, real_world)
                or not _matches_filter(path, pattern)
            ):
                continue
            try:
                kind = _fixture_headers(path).get("TEST-KIND", "").strip()
            except Exception as e:
                sys.stderr.write(f"WARN: failed to parse {path}: {e}\n")
                continue
            if kind not in selected_kinds:
                continue
            fix = _parse_fixture_for_discovery(path)
            if fix is not None:
                fixtures.append(fix)
    return fixtures


def _discover_live_stress_tex_fixtures(
    selected_kinds: set[str],
    pattern: str | None,
) -> list[Fixture]:
    if "stress" not in selected_kinds or not COMPILED_EXAMPLES_DIR.exists():
        return []
    fixtures: list[Fixture] = []
    for path in sorted(COMPILED_EXAMPLES_DIR.glob("*.tex")):
        if not _matches_filter(path, pattern):
            continue
        try:
            headers = _fixture_headers(path)
        except Exception as e:
            sys.stderr.write(f"WARN: failed to parse {path}: {e}\n")
            continue
        if (
            headers.get("TEST-KIND", "").strip() == "stress"
            and headers.get("TEST-STATUS", "").strip() in {"LIVE", "EXPLORATORY"}
        ):
            fix = _parse_fixture_for_discovery(path)
            if fix is not None:
                fixtures.append(fix)
    return fixtures


def discover_fixtures(
    selected_kinds: set[str],
    real_world: bool,
    pattern: str | None,
) -> list[Fixture]:
    """Discover selected .lvt fixtures plus LIVE stress .tex fixtures."""
    _reject_root_lvt_fixtures()
    return [
        *_discover_lvt_fixtures(selected_kinds, real_world, pattern),
        *_discover_live_stress_tex_fixtures(selected_kinds, pattern),
    ]


# ----------------------------------------------------------------------
# Summary output
# ----------------------------------------------------------------------


def _extract_brief_diagnostic(failures: list[str]) -> tuple[list[str], int]:
    """Extract first 10 non-blank lines from failure diagnostics.
    Returns (lines, suppressed_count) where suppressed_count is remaining non-blank lines.
    """
    all_lines = []
    for f in failures:
        all_lines.extend(f.split("\n"))
    non_blank = [line for line in all_lines if line.strip()]
    first_10 = non_blank[:10]
    suppressed = len(non_blank) - len(first_10)
    return first_10, suppressed


def summarize(results: list[TestResult], engine: str, verbose: bool, brief: bool = False) -> int:
    total = len(results)
    passed = sum(1 for r in results if r.passed and not r.skipped)
    failed = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    pinned_broken = sum(1 for r in results if r.fixture.pins_known_broken and not r.passed)

    if brief:
        print("=" * 72)
        print(f"codependent.sty test runner — engine: {engine}")
        print("=" * 72)
        print()
        # Brief output: FAIL/SKIP lines only
        for r in results:
            if r.skipped:
                print(f"{r.fixture.name} SKIP: {r.skip_reason}")
            elif not r.passed:
                print(f"{r.fixture.name} FAIL")
                diagnostic, suppressed = _extract_brief_diagnostic(r.failures)
                for line in diagnostic:
                    print(f"  {line}")
                if suppressed > 0:
                    print(f"  ... [{suppressed} more lines of diagnostic suppressed; re-run without --brief for full output]")
                print()
    else:
        print()
        print("=" * 72)
        print(f"codependent.sty test runner — engine: {engine}")
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

        # Skipped tests (typically: codependent.sty not yet implemented).
        if skipped > 0:
            print()
            print(f"SKIPPED ({skipped}):")
            for r in results:
                if r.skipped:
                    print(f"  {r.fixture.name}: {r.skip_reason}")

    # Identify passing LIVE integration/stress fixtures that lack TEST-PDF-*.
    def _has_pdf_directives(fix: Fixture) -> bool:
        try:
            parsed = parse_test_kind_headers(fix.path)
        except Exception:
            return True  # assume covered on parse/read error; avoid false-alarm
        return any(
            entry.get("key", "").startswith("TEST-PDF-")
            for entry in parsed.get("entries", [])
        )

    no_pdf_fixtures = [
        r for r in results
        if r.passed
        and not r.skipped
        and r.fixture.kind in {"integration", "stress"}
        and r.fixture.status == "LIVE"
        and not _has_pdf_directives(r.fixture)
    ]
    n_no_pdf = len(no_pdf_fixtures)

    print()
    print("=" * 72)
    print(
        f"TOTAL: {total}  passed={passed}  failed={failed}  "
        f"skipped={skipped}  pinned-broken={pinned_broken}  "
        f"no-pdf-assertions={n_no_pdf}"
    )
    print("=" * 72)

    if pinned_broken > 0:
        print(
            f"\nNOTE: {pinned_broken} test(s) intentionally pin known-broken "
            f"behaviour (TEST-PINS-KNOWN-BROKEN: yes). They are reported as "
            f"FAILED in the summary but do NOT contribute to the runner's "
            f"exit code. They flag intentional hazards documented in the "
            f"design, and will need to be "
            f"rewritten when the underlying issue is fixed."
        )

    if n_no_pdf > 0:
        print(
            f"\nWARNING: {n_no_pdf} passing integration/stress fixture(s) have no "
            f"TEST-PDF-* assertions — visible-output regressions may be invisible."
        )
        for r in no_pdf_fixtures:
            try:
                rel_path = r.fixture.path.relative_to(PROJECT_ROOT)
            except ValueError:
                rel_path = r.fixture.path
            print(f"  - {rel_path}")

    # Exit code: non-zero only on real failures.
    real_failures = failed - pinned_broken
    return 0 if real_failures == 0 else 1


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="run-tests.py",
        description="codependent.sty test runner",
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
    parser.add_argument("--brief", action="store_true", help="emit only failing/skipped fixtures (no PASS lines); ~80%% token savings for agent sessions")
    parser.add_argument("--unit", action="store_true", help="run TEST-KIND: unit fixtures (additive with --integration/--visual)")
    parser.add_argument("--integration", action="store_true", help="run TEST-KIND: integration fixtures (additive with --unit/--visual)")
    parser.add_argument("--visual", action="store_true", help="run TEST-KIND: stress fixtures (additive with --unit/--integration)")
    parser.add_argument("--unit-only", action="store_true", help="deprecated alias for --unit")
    parser.add_argument("--integration-only", action="store_true", help="deprecated alias for --integration")
    parser.add_argument("--real-world", action="store_true", help="include real-world arxiv-corpus fixtures")
    parser.add_argument("--full", action="store_true", help="run unit + integration + stress fixtures (default when no kind flag is specified)")
    parser.add_argument("--check-test-index", action="store_true", help="CI mode: fail if generated testfiles/test-index.md is stale; do not repair it")
    parser.add_argument(
        "--census",
        action="store_true",
        help="run only TEST-CENSUS fixtures and emit testfiles/output/*.census.json",
    )
    args = parser.parse_args()

    _reject_root_lvt_fixtures()
    index_rc = sync_test_index(check=args.check_test_index)
    if index_rc != 0:
        return index_rc

    # Engine binary.
    engine_bin = assert_engine_available(args.engine)

    # System TeX notice.
    sys.stderr.write(
        f"codependent.sty test runner — using system TeX: {engine_bin}\n"
        f"NOTE: Run inside `nix develop` to enable PDF assertion tools\n"
        f"      (mutool, qpdf). TeX Live is provided system-wide.\n\n"
    )

    # PDF tool notice.
    if PDF_TEXT_TOOL:
        sys.stderr.write(f"PDF text extraction: {PDF_TEXT_TOOL}\n")
    else:
        sys.stderr.write(
            "NOTE: PDF text tool not found (mutool or pdftotext). "
            "Tests with TEST-PDF-CONTAINS / TEST-PDF-NOT assertions will FAIL. "
            "Run inside 'nix develop' to enable.\n"
        )
    if PDF_LINK_TOOL:
        sys.stderr.write(f"PDF link counting:   {PDF_LINK_TOOL}\n")
    else:
        sys.stderr.write(
            "NOTE: PDF link tool not found (mutool or qpdf). "
            "Tests with TEST-PDF-LINKS assertions will FAIL. "
            "Run inside 'nix develop' to enable.\n"
        )
    if PDF_STEXT_TOOL:
        sys.stderr.write(f"PDF structural:      {PDF_STEXT_TOOL}\n")
    else:
        sys.stderr.write(
            "NOTE: mutool not found. Tests with TEST-PDF-STEXT / TEST-PDF-OBJECTS "
            "assertions will FAIL. Run inside 'nix develop' to enable.\n"
        )
    if PDF_QPDF_TOOL:
        sys.stderr.write(f"PDF object links:    {PDF_QPDF_TOOL}\n")
    else:
        sys.stderr.write(
            "NOTE: qpdf not found. Tests with TEST-PDF-LINK-DEST / "
            "TEST-PDF-DEST-EXISTS / TEST-PDF-NO-ORPHAN-LINKS assertions will FAIL. "
            "Run inside 'nix develop' to enable.\n"
        )
    sys.stderr.write("\n")

    # Discover fixtures. Kind flags are additive; --full/no kind flag means all.
    if args.unit_only:
        sys.stderr.write("WARNING: --unit-only is deprecated, use --unit\n")
        args.unit = True
    if args.integration_only:
        sys.stderr.write("WARNING: --integration-only is deprecated, use --integration\n")
        args.integration = True

    selected_kinds = set()
    if args.unit:
        selected_kinds.add("unit")
    if args.integration:
        selected_kinds.add("integration")
    if args.visual:
        selected_kinds.add("stress")
    if args.full or not selected_kinds:
        selected_kinds = {"unit", "integration", "stress"}

    fixtures = discover_fixtures(selected_kinds, args.real_world, args.filter)
    if args.census:
        fixtures = [fix for fix in fixtures if fix.census]

    if not fixtures:
        if args.census:
            sys.stderr.write("No TEST-CENSUS fixtures matched the filter.\n")
        else:
            sys.stderr.write("No fixtures matched the filter.\n")
        return 0

    sys.stderr.write(f"Discovered {len(fixtures)} fixture(s)\n\n")

    # Run.
    results = []
    for fix in fixtures:
        if not args.brief:
            sys.stderr.write(f"  {fix.name} ...")
            sys.stderr.flush()
        result = run_fixture(
            fix,
            engine_bin,
            args.keep_temp,
            args.verbose,
            force_census=args.census,
        )
        if not args.brief:
            if result.skipped:
                sys.stderr.write(" SKIP\n")
            elif result.passed:
                sys.stderr.write(f" PASS ({result.duration_ms}ms)\n")
            else:
                marker = " [PINS-KNOWN-BROKEN]" if fix.pins_known_broken else ""
                sys.stderr.write(f" FAIL{marker} ({result.duration_ms}ms)\n")
        results.append(result)

    return summarize(results, args.engine, args.verbose, args.brief)


if __name__ == "__main__":
    sys.exit(main())
