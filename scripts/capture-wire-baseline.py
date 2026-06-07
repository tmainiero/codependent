#!/usr/bin/env python3
"""
scripts/capture-wire-baseline.py

Compile all census fixtures + 3 stress variants, sha256 their final-pass
.aux/.cdp outputs, and write a manifest to testfiles/baselines/<wave>/.

Run under nix develop:
  nix develop --command python3 scripts/capture-wire-baseline.py
      # no-arg self-test: verifies DEFAULT_WAVE resolution without writes
  nix develop --command python3 scripts/capture-wire-baseline.py --wave W05-PARA-ORPHAN-FIX
  nix develop --command python3 scripts/capture-wire-baseline.py \\
      --wave W05-PARA-ORPHAN-FIX \\
      --manifest testfiles/baselines/W05-PARA-ORPHAN-FIX/baseline.sha256.json
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TESTFILES_DIR = PROJECT_ROOT / "testfiles"
COMPILED_EXAMPLES_DIR = TESTFILES_DIR / "compiled-examples"
BASELINE_SIZES = PROJECT_ROOT / ".claude" / "baseline-sizes.json"

# W05-STRESS-WARNINGS P02 rotates the default wire baseline to the
# current canonical stress-warnings manifest.  A no-argument invocation
# self-tests this resolution and exits before writing; pass --wave to capture.
_DEFAULT_WAVE = "W05-STRESS-WARNINGS"
_DEFAULT_MANIFEST_DIR = PROJECT_ROOT / "testfiles" / "baselines" / _DEFAULT_WAVE
MANIFEST_DIR = _DEFAULT_MANIFEST_DIR
MANIFEST_PATH = _DEFAULT_MANIFEST_DIR / "baseline.sha256.json"
DEBUG_DIR = (
    PROJECT_ROOT / ".claude" / "comms" / "waves" / _DEFAULT_WAVE / "baseline-raw"
)

STY_FILE = PROJECT_ROOT / "codependent.sty"
RENDER_STY_FILE = PROJECT_ROOT / "codependent-render.sty"
LTXML_FILE = PROJECT_ROOT / "codependent.ltxml"

INJECT_L3BUILD_NOOPS = (
    "% ---- l3build regression-test marker no-ops"
    " (injected by capture-wire-baseline.py) ----\n"
    "\\def\\START{}\n"
    "\\def\\END{}\n"
    "\\def\\OMIT{}\n"
    "\\def\\OMITS{}\n"
    "\\def\\TIMO{}\n"
    "\\long\\def\\TEST#1#2{}\n"
    "% ---- end l3build no-op injection ----\n"
)

STRESS_VARIANTS = [
    "stress-ta-appendix-gray",
    "stress-ta-inline",
    "stress-ta-inline-gray",
    "stress-backends-tcolorbox-appendix",
    "stress-backends-tcolorbox-inline",
    "stress-backends-tcolorbox-inline-gray",
    "stress-backends-keytheorems-appendix",
    "stress-backends-keytheorems-inline",
    "stress-backends-keytheorems-inline-gray",
]

# New backend fixtures that have stable wire output worth pinning but do NOT
# carry traceability census ratchets (wire baseline and census ratchet are
# separate gates — see .claude/baseline-sizes.json for census scope).
#
# W05-BACKENDS-RICH-STRESS Wave 1 added the option-matrix and mixed-backend
# integration fixtures below; the final 4 entries are RESOLVER-SILENT parity
# fixtures that pin starred/numbered=no environments as silent no-track cases.
EXTRA_INTEGRATION_FIXTURES = [
    "integ-tcolorbox-appendix-name-link-plain",
    "integ-tcolorbox-appendix-name-link-optional-heading",
    "integ-tcolorbox-appendix-no-orphan",
    "integ-tcolorbox-phantom-no-atom",
    "integ-tcolorbox-no-double-increment",
    "integ-keytheorems-appendix-name-link-plain",
    "integ-keytheorems-appendix-name-link-optional-heading",
    "integ-keytheorems-appendix-no-orphan-body-anchor",
    "integ-keytheorems-restated-no-duplicate",
    "integ-keytheorems-getkeytheorem-replay",
    "integ-keytheorems-posthead-anchor-body-equation",
    "integ-keytheorems-storestar-tracked-errors",
    "integ-keytheorems-store-ordinary-no-regression",
    "integ-keytheorems-thmtools-restatable-star-errors",
    "integ-keytheorems-thmtools-restatable-store-ordinary",
    "integ-keytheorems-heading-custom-name-link",
    "integ-keytheorems-counter-graph-parent-within-sibling",
    "integ-keytheorems-numbered-no-heading-silent-no-track",
    "integ-keytheorems-style-builtins-posthead",
    "integ-keytheorems-renew-style-posthead-survives",
    "integ-keytheorems-shared-counter-distinct-envs",
    "integ-keytheorems-thmtools-declaretheorem-compat",
    "integ-keytheorems-mixed-amsthm-keytheorems",
    "integ-tcolorbox-breakable-page-start-dest",
    "integ-tcolorbox-nophantom-and-clearing-styles",
    "integ-tcolorbox-counter-modes-number-within-auto-counter",
    "integ-tcolorbox-phantom-empty-and-cosmetic-options-neutral",
    "integ-tcolorbox-nested-tracked-untracked",
    "integ-tcolorbox-multi-env-shared-style",
    "integ-mixed-three-backends",
    "integ-amsthm-newtheorem-star-silent-no-track",
    "integ-ntheorem-newtheorem-star-silent-no-track",
    "integ-tcolorbox-starred-explicit-silent-no-track",
    "integ-keytheorems-numbered-no-silent-no-track",
    # W05-PARA-ORPHAN-FIX new fixtures (P02 + P04)
    "integ-no-orphan-para-after-tracked-env",
    "integ-keytheorems-para-teardown-no-orphan",
    "integ-tcolorbox-para-teardown-no-orphan",
    "integ-thmtools-para-teardown-no-orphan",
    "integ-ntheorem-para-teardown-no-orphan",
]


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> "str | None":
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

def _find_tool(name: str) -> Path:
    result = subprocess.run(
        ["which", name], capture_output=True, text=True
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    raise RuntimeError(f"{name!r} not found in PATH — run under nix develop")


def find_engine() -> Path:
    return _find_tool("pdflatex")


def find_qpdf() -> Path:
    return _find_tool("qpdf")


def find_latexmk() -> Path:
    return _find_tool("latexmk")


# ---------------------------------------------------------------------------
# Workspace setup
# ---------------------------------------------------------------------------

def copy_package_files(target_dir: Path) -> None:
    shutil.copy(STY_FILE, target_dir / "codependent.sty")
    if RENDER_STY_FILE.exists():
        shutil.copy(RENDER_STY_FILE, target_dir / "codependent-render.sty")
    if LTXML_FILE.exists():
        shutil.copy(LTXML_FILE, target_dir / "codependent.ltxml")


# ---------------------------------------------------------------------------
# Fixture discovery
# ---------------------------------------------------------------------------

def find_fixture_files() -> "dict[str, Path]":
    """Scan integration/ and unit/ dirs; return {test-name: lvt-path}."""
    name_to_path: "dict[str, Path]" = {}
    for search_dir in [
        TESTFILES_DIR / "integration",
        TESTFILES_DIR / "unit",
    ]:
        for lvt in sorted(search_dir.glob("*.lvt")):
            content = lvt.read_text(encoding="utf-8", errors="replace")
            m = re.search(
                r"^%{1,2}\s+TEST-NAME:\s*(\S+)", content, re.MULTILINE
            )
            if m:
                name_to_path[m.group(1)] = lvt
    return name_to_path


def extract_warm_mutation(fixture_path: Path) -> "str | None":
    content = fixture_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"^%{1,2}\s+TEST-WARM-MUTATION:\s*(.+)$", content, re.MULTILINE
    )
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def _run_pdflatex(engine: Path, name: str, cwd: Path, n_passes: int) -> bool:
    for _ in range(n_passes):
        result = subprocess.run(
            [
                str(engine),
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"{name}.tex",
            ],
            cwd=str(cwd),
            capture_output=True,
        )
        if result.returncode != 0:
            return False
    return True


def _copy_debug(src: Path, dest_name: str) -> None:
    if src.exists():
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, DEBUG_DIR / dest_name)


def compile_regular(
    fixture_path: Path, name: str, n_passes: int = 3
) -> "tuple[str | None, str | None]":
    """3-pass cold compile; returns (aux_sha, cdp_sha)."""
    with tempfile.TemporaryDirectory(
        prefix=f"codep-baseline-{name}-"
    ) as tmp:
        tmp_path = Path(tmp)
        copy_package_files(tmp_path)
        local_tex = tmp_path / f"{name}.tex"
        local_tex.write_text(
            INJECT_L3BUILD_NOOPS
            + fixture_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        engine = find_engine()
        ok = _run_pdflatex(engine, name, tmp_path, n_passes)
        if not ok:
            print(
                f"  WARNING: pdflatex failed for {name!r}", file=sys.stderr
            )

        aux_sha = sha256_file(tmp_path / f"{name}.aux")
        cdp_sha = sha256_file(tmp_path / f"{name}.cdp")

        _copy_debug(tmp_path / f"{name}.aux", f"{name}.aux")
        _copy_debug(tmp_path / f"{name}.cdp", f"{name}.cdp")

        return aux_sha, cdp_sha


def compile_warm_changed(
    fixture_path: Path, name: str
) -> "tuple[str | None, str | None]":
    """Apply warm mutation in-place, compile 2 passes; returns (aux_sha, cdp_sha)."""
    mutation = extract_warm_mutation(fixture_path)
    if not mutation:
        print(
            f"  WARNING: no TEST-WARM-MUTATION in {fixture_path}",
            file=sys.stderr,
        )
        return None, None

    original_content = fixture_path.read_text(encoding="utf-8")
    try:
        mut_result = subprocess.run(
            mutation,
            shell=True,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if mut_result.returncode != 0:
            print(
                f"  WARNING: mutation failed for {name!r}: {mutation}",
                file=sys.stderr,
            )
            return None, None

        mutated_content = fixture_path.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory(
            prefix=f"codep-baseline-{name}-wc-"
        ) as tmp:
            tmp_path = Path(tmp)
            copy_package_files(tmp_path)
            (tmp_path / f"{name}.tex").write_text(
                INJECT_L3BUILD_NOOPS + mutated_content, encoding="utf-8"
            )
            engine = find_engine()
            ok = _run_pdflatex(engine, name, tmp_path, 2)
            if not ok:
                print(
                    f"  WARNING: pdflatex failed for {name!r} [warm-changed]",
                    file=sys.stderr,
                )

            aux_sha = sha256_file(tmp_path / f"{name}.aux")
            cdp_sha = sha256_file(tmp_path / f"{name}.cdp")

            tag = f"{name}[warm-changed]"
            _copy_debug(tmp_path / f"{name}.aux", f"{tag}.aux")
            _copy_debug(tmp_path / f"{name}.cdp", f"{tag}.cdp")

            return aux_sha, cdp_sha
    finally:
        fixture_path.write_text(original_content, encoding="utf-8")


def compile_stress(
    variant_name: str,
) -> "tuple[str | None, str | None, str | None]":
    """Compile a stress variant via latexmk; returns (aux_sha, cdp_sha, pdf_objects_sha)."""
    fixture_path = COMPILED_EXAMPLES_DIR / f"{variant_name}.tex"
    if not fixture_path.exists():
        print(
            f"  WARNING: stress fixture not found: {fixture_path}",
            file=sys.stderr,
        )
        return None, None, None

    with tempfile.TemporaryDirectory(
        prefix=f"codep-baseline-stress-{variant_name}-"
    ) as tmp:
        tmp_path = Path(tmp)

        # Mirror _prepare_stress_workspace from run-tests.py
        compiled_dir = tmp_path / "testfiles" / "compiled-examples"
        compiled_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixture_path, compiled_dir / fixture_path.name)
        shutil.copy(
            COMPILED_EXAMPLES_DIR / ".latexmkrc", compiled_dir / ".latexmkrc"
        )
        support_src = TESTFILES_DIR / "support"
        if support_src.exists():
            shutil.copytree(support_src, tmp_path / "testfiles" / "support")
        copy_package_files(tmp_path)

        latexmk = find_latexmk()
        lmk_result = subprocess.run(
            [
                str(latexmk),
                "-pdf",
                "-interaction=nonstopmode",
                variant_name,
            ],
            cwd=str(compiled_dir),
            capture_output=True,
        )
        if lmk_result.returncode != 0:
            stderr_tail = lmk_result.stderr[-2000:].decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(
                f"latexmk failed (exit {lmk_result.returncode}) "
                f"for stress variant {variant_name!r}:\n{stderr_tail}"
            )

        aux_path = tmp_path / "texbuild" / f"{variant_name}.aux"
        cdp_path = tmp_path / "texbuild" / f"{variant_name}.cdp"
        pdf_path = tmp_path / "pdf-out" / f"{variant_name}.pdf"

        aux_sha = sha256_file(aux_path)
        cdp_sha = sha256_file(cdp_path)

        if not pdf_path.exists():
            raise RuntimeError(
                f"latexmk exited 0 but PDF not found at {pdf_path}; "
                f"check $out_dir in {compiled_dir / '.latexmkrc'}"
            )
        qpdf = find_qpdf()
        qpdf_result = subprocess.run(
            [str(qpdf), "--json", str(pdf_path)],
            capture_output=True,
            text=True,
        )
        if qpdf_result.returncode != 0:
            raise RuntimeError(
                f"qpdf failed (exit {qpdf_result.returncode}) "
                f"on {pdf_path}:\n{qpdf_result.stderr[-1000:]}"
            )
        obj_json = qpdf_result.stdout
        # Strip volatile fields before hashing (Producer, CreationDate, /ID).
        # /ID is a two-entry array of random binary hashes that change every
        # compile (PDF spec §7.5.5); strip both entries.
        obj_json = re.sub(
            r'"Producer"\s*:\s*"[^"]*"',
            '"Producer": ""',
            obj_json,
        )
        obj_json = re.sub(
            r'"CreationDate"\s*:\s*"[^"]*"',
            '"CreationDate": ""',
            obj_json,
        )
        obj_json = re.sub(
            r'"/ID"\s*:\s*\[[^\]]*\]',
            '"/ID": []',
            obj_json,
        )
        pdf_objects_sha = sha256_text(obj_json)

        # Write debug copy
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"{variant_name}.qpdf.json").write_text(
            obj_json, encoding="utf-8"
        )

        _copy_debug(aux_path, aux_path.name)
        _copy_debug(cdp_path, cdp_path.name)

        return aux_sha, cdp_sha, pdf_objects_sha


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: "list[str] | None" = None) -> "argparse.Namespace":
    parser = argparse.ArgumentParser(
        description="Capture wire-format baseline sha256 manifest."
    )
    parser.add_argument(
        "--wave",
        default=_DEFAULT_WAVE,
        help=(
            "Wave identifier (e.g. W05-XPARSE-VMODE-FIXES). "
            f"Default: {_DEFAULT_WAVE!r}"
        ),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Path to write the manifest JSON. "
            "Default: testfiles/baselines/<wave>/baseline.sha256.json"
        ),
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parse_args(argv)
    wave_id: str = args.wave

    if not argv:
        print("DEFAULT_WAVE self-test")
        print(f"Resolved wave: {wave_id}")
        print(f"Manifest path: {MANIFEST_PATH}")
        if wave_id != "W05-STRESS-WARNINGS":
            print(
                "ERROR: no-arg DEFAULT_WAVE did not resolve to "
                "W05-STRESS-WARNINGS",
                file=sys.stderr,
            )
            return 2
        return 0

    if args.manifest is not None:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = PROJECT_ROOT / manifest_path
    else:
        manifest_path = (
            PROJECT_ROOT / "testfiles" / "baselines" / wave_id / "baseline.sha256.json"
        )

    manifest_dir = manifest_path.parent
    debug_dir = (
        PROJECT_ROOT / ".claude" / "comms" / "waves" / wave_id / "baseline-raw"
    )

    # Monkey-patch module-level DEBUG_DIR so _copy_debug uses the right wave dir
    global DEBUG_DIR
    DEBUG_DIR = debug_dir

    print(f"{wave_id} wire-format baseline capture")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Manifest path: {manifest_path}")

    census_data = json.loads(BASELINE_SIZES.read_text(encoding="utf-8"))
    census_keys: "list[str]" = list(census_data.get("census", {}).keys())
    print(f"Census keys: {len(census_keys)}")

    fixture_map = find_fixture_files()

    results: "list[dict]" = []

    for key in census_keys:
        is_wc = key.endswith(" [warm-changed]")
        base_name = key[: -len(" [warm-changed]")] if is_wc else key

        fixture_path = fixture_map.get(base_name)
        if fixture_path is None:
            print(
                f"  ERROR: no fixture for {base_name!r}", file=sys.stderr
            )
            results.append(
                {
                    "name": key,
                    "aux_sha": None,
                    "cdp_sha": None,
                    "pdf_objects_sha": None,
                }
            )
            continue

        print(f"  {'[wc] ' if is_wc else '      '}{key}")
        if is_wc:
            aux_sha, cdp_sha = compile_warm_changed(fixture_path, base_name)
        else:
            aux_sha, cdp_sha = compile_regular(fixture_path, base_name)

        results.append(
            {
                "name": key,
                "aux_sha": aux_sha,
                "cdp_sha": cdp_sha,
                "pdf_objects_sha": None,
            }
        )

    for variant in STRESS_VARIANTS:
        print(f"  [stress] {variant}")
        aux_sha, cdp_sha, pdf_objects_sha = compile_stress(variant)
        results.append(
            {
                "name": variant,
                "aux_sha": aux_sha,
                "cdp_sha": cdp_sha,
                "pdf_objects_sha": pdf_objects_sha,
            }
        )

    for name in EXTRA_INTEGRATION_FIXTURES:
        fixture_path = fixture_map.get(name)
        if fixture_path is None:
            print(f"  ERROR: no fixture for {name!r}", file=sys.stderr)
            results.append(
                {
                    "name": name,
                    "aux_sha": None,
                    "cdp_sha": None,
                    "pdf_objects_sha": None,
                }
            )
            continue

        print(f"  [extra] {name}")
        aux_sha, cdp_sha = compile_regular(fixture_path, name, n_passes=3)
        results.append(
            {
                "name": name,
                "aux_sha": aux_sha,
                "cdp_sha": cdp_sha,
                "pdf_objects_sha": None,
            }
        )

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest: "dict" = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": results,
        "wave": wave_id,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nManifest → {manifest_path}")
    print(f"Fixtures captured: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
