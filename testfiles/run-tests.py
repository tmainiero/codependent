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
import json
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

# Path of THIS script: tools/codependent/testfiles/run-tests.py
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # tools/codependent/
UNIT_DIR = SCRIPT_DIR / "unit"
INTEGRATION_DIR = SCRIPT_DIR / "integration"
REAL_WORLD_DIR = SCRIPT_DIR / "real-world" / "wrappers"

# Where the .sty file lives. The runner copies it into the temp work dir
# so each test sees a clean kpse search path.
STY_FILE = PROJECT_ROOT / "codependent.sty"
RENDER_STY_FILE = PROJECT_ROOT / "codependent-render.sty"
LTXML_FILE = PROJECT_ROOT / "codependent.ltxml"  # may not exist yet


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
    "TEST-CDP-CONTAINS": "sbl_contains",  # may repeat
    "TEST-CDP-NOT-CONTAINS": "sbl_not_contains",  # may repeat
    "TEST-CDP-COUNT": "sbl_count",  # "<pattern> = <n>", may repeat
    "TEST-CDP-LAST-RECORD": "sbl_last_record",  # last non-empty line must contain this
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
}

REPEATING_KEYS = {
    "log_not", "log_contains",
    "sbl_contains", "sbl_not_contains", "sbl_count",
    "aux_contains", "aux_not_contains",
    "pdf_contains", "pdf_not",
    "pdf_stext", "pdf_stext_not",
    "pdf_objects", "pdf_objects_not",
    "pdf_link_dest", "pdf_link_dest_not",
    "pdf_dest_exists", "pdf_dest_not_exists",
    "pdf_link_rect",
    "pdf_backref_targets",
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
    sbl_last_record: str = ""
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
            elif attr == "pdf_no_orphan_links":
                fix.pdf_no_orphan_links = value.lower() in ("yes", "true", "1")
            elif attr == "pdf_all_backrefs_linked":
                fix.pdf_all_backrefs_linked = value.lower() in ("yes", "true", "1")
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


@dataclasses.dataclass
class PdfLinkInfo:
    """A single link annotation extracted from PDF objects."""
    obj_id: str
    rect: list  # [x1, y1, x2, y2]
    dest: str   # destination name (e.g. "u:lemma.8")


@dataclasses.dataclass
class PdfLinkObjects:
    """Structured PDF link/destination data extracted via qpdf --json=2."""
    links: list   # list of PdfLinkInfo
    destinations: set  # set of named destination strings


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

    # Collect named destinations from the Names tree.
    destinations: set[str] = set()
    dests_root = _find_names_root(objs)
    if dests_root is not None:
        visited: set[str] = set()
        dest_names = _collect_names_from_tree(objs, dests_root, visited)
        destinations.update(dest_names)

    return PdfLinkObjects(links=links, destinations=destinations)


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

    # Find all <line> elements containing "Used in"
    line_re = re.compile(
        r'<line\s+bbox="([^"]+)"[^>]*text="(Used in[^"]*)"'
    )
    for m in line_re.finditer(stext_xml):
        bbox_str = m.group(1)
        text = m.group(2)
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

        results.append(_BackrefLine(
            text=text,
            entries=entries,
            bbox=bbox,
            page_height=page_height,
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
            f"codependent.sty not found at {STY_FILE} (implementation not landed yet)"
        )
        return result

    # Each fixture runs in its own temp dir so .aux/.cdp files don't collide.
    with tempfile.TemporaryDirectory(prefix=f"codep-test-{fix.name}-") as tmp:
        tmp_path = Path(tmp)
        # Copy the fixture and the .sty into the temp dir.
        local_lvt = tmp_path / f"{fix.name}.tex"  # rename to .tex for engine
        shutil.copy(fix.path, local_lvt)
        # Inject l3build regression-test marker no-ops at the top of the
        # fixture so \START / \END do not error.  l3build itself provides
        # these via regression-test.tex; our standalone runner does not.
        content = local_lvt.read_text(encoding="utf-8")
        local_lvt.write_text(INJECT_L3BUILD_NOOPS + content, encoding="utf-8")
        shutil.copy(STY_FILE, tmp_path / "codependent.sty")
        if RENDER_STY_FILE.exists():
            shutil.copy(RENDER_STY_FILE, tmp_path / "codependent-render.sty")
        if LTXML_FILE.exists():
            shutil.copy(LTXML_FILE, tmp_path / "codependent.ltxml")

        # Run the engine `rerun` times to populate .aux + .cdp.
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
        sbl_file = tmp_path / f"{fix.name}.cdp"

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

        # 4. CDP assertions.
        for s in fix.sbl_contains:
            if s not in sbl_text:
                result.failures.append(f"cdp missing required string: {s}")
        for s in fix.sbl_not_contains:
            if s in sbl_text:
                result.failures.append(f"cdp contains forbidden string: {s}")

        # 5. CDP counts: format "<pattern> = <n>".
        for spec in fix.sbl_count:
            try:
                pat, expected = spec.rsplit("=", 1)
                pat = pat.strip()
                expected_n = int(expected.strip())
            except ValueError:
                result.failures.append(f"malformed TEST-CDP-COUNT: {spec}")
                continue
            actual = sbl_text.count(pat)
            if actual != expected_n:
                result.failures.append(
                    f"cdp count for {pat!r}: expected {expected_n}, got {actual}"
                )

        # 6. AUX assertions.
        for s in fix.aux_contains:
            if s not in aux_text:
                result.failures.append(f"aux missing required string: {s}")
        for s in fix.aux_not_contains:
            if s in aux_text:
                result.failures.append(f"aux contains forbidden string: {s}")

        # 7. atoms_min: count \codep@cdp@atom records.
        if fix.atoms_min > 0:
            atom_count = sbl_text.count("\\codep@cdp@atom{")
            if atom_count < fix.atoms_min:
                result.failures.append(
                    f"atom count: expected >= {fix.atoms_min}, got {atom_count}"
                )

        # 8. sbl_last_record: the last NON-EMPTY line of .cdp must
        #    contain the specified string. Stronger than sbl_contains
        #    because it pins position. Used by test-sbl-end-marker to
        #    enforce that the sentinel is the file-final record, not
        #    just present somewhere in the file.
        if fix.sbl_last_record:
            non_empty_lines = [
                line for line in sbl_text.splitlines()
                if line.strip()
            ]
            if not non_empty_lines:
                result.failures.append(
                    f"cdp last-record check: file is empty, expected {fix.sbl_last_record!r}"
                )
            elif fix.sbl_last_record not in non_empty_lines[-1]:
                result.failures.append(
                    f"cdp last-record: expected {fix.sbl_last_record!r}, "
                    f"got last non-empty line: {non_empty_lines[-1]!r}"
                )

        # 9. PDF content assertions (TEST-PDF-CONTAINS, TEST-PDF-NOT,
        #    TEST-PDF-LINKS).  Only run when at least one PDF directive
        #    is present.  Skipped with a warning when no PDF extraction
        #    tool is available on PATH.
        has_pdf_checks = (fix.pdf_contains or fix.pdf_not or fix.pdf_links > 0
                          or fix.pdf_stext or fix.pdf_stext_not
                          or fix.pdf_objects or fix.pdf_objects_not
                          or fix.pdf_link_dest or fix.pdf_link_dest_not
                          or fix.pdf_link_count >= 0
                          or fix.pdf_dest_exists or fix.pdf_dest_not_exists
                          or fix.pdf_link_rect or fix.pdf_no_orphan_links
                          or fix.pdf_all_backrefs_linked
                          or fix.pdf_backref_targets)
        if has_pdf_checks:
            pdf_file = tmp_path / f"{fix.name}.pdf"
            if not pdf_file.exists():
                result.failures.append(
                    "pdf assertions present but no PDF was produced"
                )
            elif PDF_TEXT_TOOL is None and (fix.pdf_contains or fix.pdf_not):
                sys.stderr.write(
                    f"  WARN: skipping PDF text checks for {fix.name} "
                    f"(no mutool or pdftotext on PATH)\n"
                )
            else:
                # Text-based checks.
                if fix.pdf_contains or fix.pdf_not:
                    pdf_text = _extract_pdf_text(pdf_file)
                    if pdf_text is None:
                        result.failures.append(
                            "pdf text extraction failed "
                            f"(tool: {PDF_TEXT_TOOL})"
                        )
                    else:
                        for s in fix.pdf_contains:
                            if s not in pdf_text:
                                result.failures.append(
                                    f"pdf missing required text: {s!r}"
                                )
                        for s in fix.pdf_not:
                            if s in pdf_text:
                                result.failures.append(
                                    f"pdf contains forbidden text: {s!r}"
                                )

                # Link count check.
                if fix.pdf_links > 0:
                    if PDF_LINK_TOOL is None:
                        sys.stderr.write(
                            f"  WARN: skipping PDF link check for {fix.name} "
                            f"(no mutool or qpdf on PATH)\n"
                        )
                    else:
                        link_count = _count_pdf_links(pdf_file)
                        if link_count is None:
                            result.failures.append(
                                "pdf link counting failed "
                                f"(tool: {PDF_LINK_TOOL})"
                            )
                        elif link_count < fix.pdf_links:
                            result.failures.append(
                                f"pdf links: expected >= {fix.pdf_links}, "
                                f"got {link_count}"
                            )

                # 10. Structured text assertions (positions, fonts).
                if fix.pdf_stext or fix.pdf_stext_not:
                    if PDF_STEXT_TOOL is None:
                        sys.stderr.write(
                            f"  WARN: skipping PDF stext checks for {fix.name} "
                            f"(no mutool on PATH)\n"
                        )
                    else:
                        stext_xml = _extract_pdf_stext(pdf_file)
                        if stext_xml is None:
                            result.failures.append(
                                "pdf stext extraction failed"
                            )
                        else:
                            for pat in fix.pdf_stext:
                                if not re.search(pat, stext_xml):
                                    result.failures.append(
                                        f"pdf stext missing pattern: {pat!r}"
                                    )
                            for pat in fix.pdf_stext_not:
                                if re.search(pat, stext_xml):
                                    result.failures.append(
                                        f"pdf stext matched forbidden pattern: {pat!r}"
                                    )

                # 11. PDF object assertions (link annotations, destinations).
                if fix.pdf_objects or fix.pdf_objects_not:
                    if PDF_STEXT_TOOL is None:
                        sys.stderr.write(
                            f"  WARN: skipping PDF object checks for {fix.name} "
                            f"(no mutool on PATH)\n"
                        )
                    else:
                        obj_dump = _extract_pdf_objects(pdf_file)
                        if obj_dump is None:
                            result.failures.append(
                                "pdf object extraction failed"
                            )
                        else:
                            for pat in fix.pdf_objects:
                                if not re.search(pat, obj_dump):
                                    result.failures.append(
                                        f"pdf objects missing pattern: {pat!r}"
                                    )
                            for pat in fix.pdf_objects_not:
                                if re.search(pat, obj_dump):
                                    result.failures.append(
                                        f"pdf objects matched forbidden pattern: {pat!r}"
                                    )

                # 12. Object-level PDF link verification (qpdf --json=2).
                has_qpdf_checks = (
                    fix.pdf_link_dest or fix.pdf_link_dest_not
                    or fix.pdf_link_count >= 0
                    or fix.pdf_dest_exists or fix.pdf_dest_not_exists
                    or fix.pdf_link_rect or fix.pdf_no_orphan_links
                )
                if has_qpdf_checks:
                    if PDF_QPDF_TOOL is None:
                        sys.stderr.write(
                            f"  WARN: skipping PDF object-level link checks "
                            f"for {fix.name} (no qpdf on PATH)\n"
                        )
                    else:
                        link_data = _extract_pdf_link_objects(pdf_file)
                        if link_data is None:
                            result.failures.append(
                                "pdf link object extraction failed "
                                f"(tool: {PDF_QPDF_TOOL})"
                            )
                        else:
                            # TEST-PDF-LINK-DEST: regex on link dest names
                            for pat in fix.pdf_link_dest:
                                if not any(re.search(pat, lnk.dest) for lnk in link_data.links):
                                    result.failures.append(
                                        f"pdf link dest missing pattern: {pat!r}"
                                    )

                            # TEST-PDF-LINK-DEST-NOT: dest must NOT match
                            for pat in fix.pdf_link_dest_not:
                                for lnk in link_data.links:
                                    if re.search(pat, lnk.dest):
                                        result.failures.append(
                                            f"pdf link dest matched forbidden "
                                            f"pattern: {pat!r} (on {lnk.dest!r})"
                                        )
                                        break

                            # TEST-PDF-LINK-COUNT: exact count
                            if fix.pdf_link_count >= 0:
                                actual = len(link_data.links)
                                if actual != fix.pdf_link_count:
                                    result.failures.append(
                                        f"pdf link count: expected "
                                        f"{fix.pdf_link_count}, got {actual}"
                                    )

                            # TEST-PDF-DEST-EXISTS: regex on named dests
                            for pat in fix.pdf_dest_exists:
                                if not any(re.search(pat, d) for d in link_data.destinations):
                                    result.failures.append(
                                        f"pdf named dest missing pattern: {pat!r}"
                                    )

                            # TEST-PDF-DEST-NOT-EXISTS: named dest must NOT match
                            for pat in fix.pdf_dest_not_exists:
                                for d in link_data.destinations:
                                    if re.search(pat, d):
                                        result.failures.append(
                                            f"pdf named dest matched forbidden "
                                            f"pattern: {pat!r} (on {d!r})"
                                        )
                                        break

                            # TEST-PDF-LINK-RECT: "<dest> <x1> <y1> <x2> <y2> <tol>"
                            for spec in fix.pdf_link_rect:
                                parts = spec.split()
                                if len(parts) != 6:
                                    result.failures.append(
                                        f"malformed TEST-PDF-LINK-RECT: {spec}"
                                    )
                                    continue
                                dest_pat = parts[0]
                                try:
                                    ex = [float(x) for x in parts[1:5]]
                                    tol = float(parts[5])
                                except ValueError:
                                    result.failures.append(
                                        f"malformed TEST-PDF-LINK-RECT coords: {spec}"
                                    )
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
                                    result.failures.append(
                                        f"pdf link rect: no link matching "
                                        f"dest={dest_pat!r} with rect "
                                        f"~{ex} (tol={tol})"
                                    )

                            # TEST-PDF-NO-ORPHAN-LINKS: every link dest
                            # must resolve to a named destination.
                            if fix.pdf_no_orphan_links:
                                orphans = []
                                for lnk in link_data.links:
                                    if not lnk.dest:
                                        continue  # no named dest (page ref)
                                    if lnk.dest not in link_data.destinations:
                                        orphans.append(lnk.dest)
                                if orphans:
                                    unique = sorted(set(orphans))
                                    result.failures.append(
                                        f"pdf orphan links ({len(orphans)}): "
                                        f"dests not in Names tree: "
                                        f"{', '.join(unique[:10])}"
                                    )

                # 13. Backref hyperlink verification (TEST-PDF-ALL-BACKREFS-LINKED,
                #     TEST-PDF-BACKREF-TARGETS). Requires both mutool (stext) and
                #     qpdf (link annotations).
                has_backref_checks = (
                    fix.pdf_all_backrefs_linked or fix.pdf_backref_targets
                )
                if has_backref_checks:
                    if PDF_STEXT_TOOL is None or PDF_QPDF_TOOL is None:
                        missing = []
                        if PDF_STEXT_TOOL is None:
                            missing.append("mutool")
                        if PDF_QPDF_TOOL is None:
                            missing.append("qpdf")
                        sys.stderr.write(
                            f"  WARN: skipping backref link checks for "
                            f"{fix.name} (missing: {', '.join(missing)})\n"
                        )
                    else:
                        # Extract stext for "Used in" line positions.
                        stext_xml = _extract_pdf_stext(pdf_file)
                        if stext_xml is None:
                            result.failures.append(
                                "backref check: stext extraction failed"
                            )
                        else:
                            backref_lines = _parse_backref_lines_from_stext(
                                stext_xml
                            )
                            # Extract link objects for backref checks.
                            br_link_data = _extract_pdf_link_objects(pdf_file)
                            if br_link_data is None:
                                result.failures.append(
                                    "backref check: qpdf extraction failed"
                                )
                            else:
                                # TEST-PDF-ALL-BACKREFS-LINKED
                                if fix.pdf_all_backrefs_linked:
                                    if not backref_lines:
                                        result.failures.append(
                                            "all-backrefs-linked: no 'Used in'"
                                            " lines found in PDF"
                                        )
                                    for bline in backref_lines:
                                        overlapping = _links_overlapping_line(
                                            br_link_data, bline
                                        )
                                        n_entries = len(bline.entries)
                                        n_links = len(overlapping)
                                        if n_links < n_entries:
                                            result.failures.append(
                                                f"all-backrefs-linked: "
                                                f"'{bline.text}' has "
                                                f"{n_entries} entries but "
                                                f"only {n_links} covering "
                                                f"link(s)"
                                            )

                                # TEST-PDF-BACKREF-TARGETS
                                for spec in fix.pdf_backref_targets:
                                    # Format: "<atom-dest-pattern> = <d1>, <d2>"
                                    if "=" not in spec:
                                        result.failures.append(
                                            f"malformed TEST-PDF-BACKREF-"
                                            f"TARGETS: {spec}"
                                        )
                                        continue
                                    atom_pat, targets_str = spec.split("=", 1)
                                    atom_pat = atom_pat.strip()
                                    expected_dests = [
                                        d.strip()
                                        for d in targets_str.split(",")
                                        if d.strip()
                                    ]
                                    # Find the "Used in" line whose overlapping
                                    # links include destinations matching ALL of
                                    # expected_dests.  This identifies the correct
                                    # line without needing the atom's y-position.
                                    matched_line = None
                                    for bline in backref_lines:
                                        overlapping = _links_overlapping_line(
                                            br_link_data, bline
                                        )
                                        link_dests = [
                                            lnk.dest for lnk in overlapping
                                        ]
                                        # Check if all expected dest patterns
                                        # match some link in this line.
                                        all_match = True
                                        for dp in expected_dests:
                                            if not any(
                                                re.search(dp, ld)
                                                for ld in link_dests
                                            ):
                                                all_match = False
                                                break
                                        if all_match:
                                            matched_line = bline
                                            break

                                    if matched_line is None:
                                        # Try to give a helpful error: show
                                        # which lines exist and their link dests
                                        summaries = []
                                        for bline in backref_lines[:5]:
                                            ov = _links_overlapping_line(
                                                br_link_data, bline
                                            )
                                            dests = [l.dest for l in ov]
                                            summaries.append(
                                                f"'{bline.text}' -> "
                                                f"{dests[:4]}"
                                            )
                                        result.failures.append(
                                            f"backref-targets: no 'Used in' "
                                            f"line found with links matching "
                                            f"all of {expected_dests} "
                                            f"(atom pattern: {atom_pat!r}). "
                                            f"Lines found: "
                                            f"{'; '.join(summaries)}"
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
            f"design, and will need to be "
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
    parser.add_argument("--unit-only", action="store_true", help="only run unit fixtures")
    parser.add_argument("--integration-only", action="store_true", help="only run integration fixtures")
    parser.add_argument("--real-world", action="store_true", help="include real-world arxiv-corpus fixtures")
    args = parser.parse_args()

    # Engine binary.
    engine_bin = assert_engine_available(args.engine)

    # System TeX notice.
    sys.stderr.write(
        f"codependent.sty test runner — using system TeX: {engine_bin}\n"
        f"NOTE: per user direction 2026-04-09, the project's Nix flake does\n"
        f"      not yet include all required packages. System-wide texlive-full\n"
        f"      is in use as a one-time exception. Future runs should go\n"
        f"      through `nix develop` once the flake is updated.\n\n"
    )

    # PDF tool notice.
    if PDF_TEXT_TOOL:
        sys.stderr.write(f"PDF text extraction: {PDF_TEXT_TOOL}\n")
    else:
        sys.stderr.write(
            "WARN: no PDF text tool found (mutool or pdftotext). "
            "TEST-PDF-CONTAINS / TEST-PDF-NOT checks will be skipped.\n"
        )
    if PDF_LINK_TOOL:
        sys.stderr.write(f"PDF link counting:   {PDF_LINK_TOOL}\n")
    else:
        sys.stderr.write(
            "WARN: no PDF link tool found (mutool or qpdf). "
            "TEST-PDF-LINKS checks will be skipped.\n"
        )
    if PDF_STEXT_TOOL:
        sys.stderr.write(f"PDF structural:      {PDF_STEXT_TOOL}\n")
    else:
        sys.stderr.write(
            "WARN: no mutool found. TEST-PDF-STEXT / TEST-PDF-OBJECTS "
            "checks will be skipped. Install: nix-shell -p mupdf qpdf\n"
        )
    if PDF_QPDF_TOOL:
        sys.stderr.write(f"PDF object links:    {PDF_QPDF_TOOL}\n")
    else:
        sys.stderr.write(
            "WARN: no qpdf found. TEST-PDF-LINK-DEST / TEST-PDF-DEST-EXISTS / "
            "TEST-PDF-NO-ORPHAN-LINKS checks will be skipped.\n"
        )
    sys.stderr.write("\n")

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
