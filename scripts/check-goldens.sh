#!/usr/bin/env bash
# Volatile fields stripped before comparison — see scripts/normalize-pdf-json.py:
#   /ID (trailer), /CreationDate, /ModDate, /Producer, /Creator (Info objects),
#   maxobjectid (qpdf header). Two-pass probe on stress-ta-appendix-gray confirms
#   normalized JSON is identical between same-source compilations in this Nix env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXIT_CODE=0
MISSING_COUNT=0
DRIFT_COUNT=0

usage() {
    cat <<'EOF'
Usage: scripts/check-goldens.sh [--help]

For each committed golden in pdf-out/goldens/*.pdf:
  1. Recompile the corresponding stress fixture via the runner.
  2. Normalize both the golden and fresh PDF (strip volatile metadata).
  3. Diff the normalized JSON representations.
  4. Also compare extracted text via mutool draw -F stext.

Exit codes:
  0  All goldens match (or no goldens found — treated as warning, not error).
  1  One or more goldens have drifted, or normalization/compilation failed.

Missing goldens are reported but do not by themselves cause exit 1 — the
first run is expected to have no goldens. Use --strict-missing to change this.
EOF
    exit 0
}

STRICT_MISSING=false
for arg in "$@"; do
    case "$arg" in
        --help|-h) usage ;;
        --strict-missing) STRICT_MISSING=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

NORMALIZE="scripts/normalize-pdf-json.py"
if [[ ! -f "$NORMALIZE" ]]; then
    echo "error: ${NORMALIZE} not found — cannot normalize PDFs for comparison" >&2
    exit 1
fi

GOLDENS_DIR="pdf-out/goldens"
if [[ ! -d "$GOLDENS_DIR" ]]; then
    echo "[check-goldens] no goldens directory found at ${GOLDENS_DIR}"
    echo "[check-goldens] result: NO GOLDENS (run scripts/run-stress.sh then scripts/promote-golden.sh)"
    exit 0
fi

mapfile -t GOLDEN_PDFS < <(find "$GOLDENS_DIR" -maxdepth 1 -name "*.pdf" | sort)

if [[ ${#GOLDEN_PDFS[@]} -eq 0 ]]; then
    echo "[check-goldens] no goldens committed yet in ${GOLDENS_DIR}"
    echo "[check-goldens] result: NO GOLDENS — use run-stress.sh + promote-golden.sh to create initial goldens"
    if $STRICT_MISSING; then exit 1; fi
    exit 0
fi

TMPDIR_WORK=$(mktemp -d)
trap "rm -rf '${TMPDIR_WORK}'" EXIT

for GOLDEN_PDF in "${GOLDEN_PDFS[@]}"; do
    FIXTURE=$(basename "$GOLDEN_PDF" .pdf)
    MANIFEST="${GOLDENS_DIR}/${FIXTURE}-manifest.json"

    echo ""
    echo "[check-goldens] === ${FIXTURE} ==="

    # Check manifest
    if [[ ! -f "$MANIFEST" ]]; then
        echo "[check-goldens] WARNING: missing manifest for ${FIXTURE} (${MANIFEST})"
    fi

    # Check fixture source exists
    FIXTURE_TEX="testfiles/compiled-examples/${FIXTURE}.tex"
    if [[ ! -f "$FIXTURE_TEX" ]]; then
        echo "[check-goldens] MISSING: fixture source ${FIXTURE_TEX} not found"
        (( MISSING_COUNT++ )) || true
        EXIT_CODE=1
        continue
    fi

    # Recompile via runner (preserves TEST-PDF assertion machinery)
    echo "[check-goldens] recompiling via runner..."
    nix develop --command python3 testfiles/run-tests.py \
        --visual --filter "${FIXTURE}" --keep-temp \
        > "${TMPDIR_WORK}/${FIXTURE}-runner.log" 2>&1 || {
        echo "[check-goldens] FAIL: runner returned non-zero for ${FIXTURE}"
        cat "${TMPDIR_WORK}/${FIXTURE}-runner.log"
        EXIT_CODE=1
        (( DRIFT_COUNT++ )) || true
        continue
    }

    FRESH_PDF="pdf-out/${FIXTURE}.pdf"
    if [[ ! -f "$FRESH_PDF" ]]; then
        echo "[check-goldens] FAIL: runner did not produce ${FRESH_PDF}"
        EXIT_CODE=1
        (( DRIFT_COUNT++ )) || true
        continue
    fi

    # Normalize both PDFs
    NORM_GOLDEN="${TMPDIR_WORK}/${FIXTURE}-golden-norm.json"
    NORM_FRESH="${TMPDIR_WORK}/${FIXTURE}-fresh-norm.json"

    nix develop --command python3 "$NORMALIZE" "$GOLDEN_PDF" --output "$NORM_GOLDEN" || {
        echo "[check-goldens] FAIL: normalization failed for golden ${GOLDEN_PDF}"
        EXIT_CODE=1
        (( DRIFT_COUNT++ )) || true
        continue
    }
    nix develop --command python3 "$NORMALIZE" "$FRESH_PDF" --output "$NORM_FRESH" || {
        echo "[check-goldens] FAIL: normalization failed for fresh ${FRESH_PDF}"
        EXIT_CODE=1
        (( DRIFT_COUNT++ )) || true
        continue
    }

    # Structural diff (normalized JSON)
    STRUCT_DIFF="${TMPDIR_WORK}/${FIXTURE}-struct.diff"
    if diff -u "$NORM_GOLDEN" "$NORM_FRESH" > "$STRUCT_DIFF" 2>&1; then
        echo "[check-goldens] structural: MATCH"
    else
        echo "[check-goldens] structural: DRIFT (JSON diff follows)"
        head -60 "$STRUCT_DIFF"
        EXIT_CODE=1
        (( DRIFT_COUNT++ )) || true
    fi

    # Text diff via mutool
    TEXT_GOLDEN="${TMPDIR_WORK}/${FIXTURE}-golden.txt"
    TEXT_FRESH="${TMPDIR_WORK}/${FIXTURE}-fresh.txt"
    TEXT_DIFF="${TMPDIR_WORK}/${FIXTURE}-text.diff"

    nix develop --command mutool draw -F stext "$GOLDEN_PDF" \
        > "$TEXT_GOLDEN" 2>/dev/null || echo "(mutool stext failed on golden)" > "$TEXT_GOLDEN"
    nix develop --command mutool draw -F stext "$FRESH_PDF" \
        > "$TEXT_FRESH" 2>/dev/null || echo "(mutool stext failed on fresh)" > "$TEXT_FRESH"

    if diff -u "$TEXT_GOLDEN" "$TEXT_FRESH" > "$TEXT_DIFF" 2>&1; then
        echo "[check-goldens] text:        MATCH"
    else
        echo "[check-goldens] text:        DRIFT (text diff follows)"
        head -40 "$TEXT_DIFF"
        # Text drift without structural drift is a warning, not hard failure;
        # mutool stext output can vary by version. Exit code already set if struct drifted.
        echo "[check-goldens] NOTE: text drift without structural drift may indicate mutool version delta"
    fi
done

echo ""
echo "[check-goldens] === SUMMARY ==="
echo "[check-goldens] goldens checked: ${#GOLDEN_PDFS[@]}"
echo "[check-goldens] missing sources: ${MISSING_COUNT}"
echo "[check-goldens] drifted:         ${DRIFT_COUNT}"

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[check-goldens] result: ALL MATCH"
else
    echo "[check-goldens] result: DRIFT DETECTED — re-run scripts/run-stress.sh and inspect PDFs"
fi

exit "${EXIT_CODE}"
