#!/usr/bin/env bash
# compare-wire-format.sh — Diff .aux/.cdp records between baseline and current code.
#
# Usage:
#   compare-wire-format.sh baseline          # Save baseline from committed HEAD
#   compare-wire-format.sh compare           # Compile with working tree, diff against baseline
#   compare-wire-format.sh auto              # baseline + compare in one shot (stash/unstash)
#
# Compiles key integration fixtures through 3 passes and diffs the codependent
# records (codep@atomref, codep@anchormap, codep@lbltype, codep@cdp@*) between
# baseline and current. Empty diff = wire-format identity.
#
# Requires: nix develop (mutool, pdflatex, etc.)

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BASELINE_DIR="/tmp/codep-wire-baseline"
CURRENT_DIR="/tmp/codep-wire-current"
FIXTURES=(
  "integ-full-stack-below"
  "integ-full-stack-inline"
  "trinity-test"
)
PASSES=3

die() { echo "error: $1" >&2; exit 1; }

compile_fixtures() {
    local outdir="$1"
    local label="$2"
    rm -rf "$outdir"
    mkdir -p "$outdir"
    for fix in "${FIXTURES[@]}"; do
        echo "  [$label] Compiling $fix ($PASSES passes)..." >&2
        local fixdir="$outdir/$fix"
        mkdir -p "$fixdir"
        (
            cd "$fixdir"
            for i in $(seq 1 "$PASSES"); do
                TEXINPUTS="$PROJECT_DIR/testfiles/integration/:$PROJECT_DIR//:" \
                    pdflatex -interaction=nonstopmode "$fix.lvt" >/dev/null 2>&1 || true
            done
        )
    done
}

extract_records() {
    local auxfile="$1"
    grep -E 'codep@atomref|codep@anchormap|codep@lbltype|codep@cdp@' "$auxfile" 2>/dev/null | sort
}

extract_cdp_records() {
    local cdpfile="$1"
    cat "$cdpfile" 2>/dev/null | sort
}

do_baseline() {
    echo "Saving wire-format baseline from HEAD..." >&2
    local stashed=false
    if ! git -C "$PROJECT_DIR" diff --quiet codependent.sty 2>/dev/null; then
        git -C "$PROJECT_DIR" stash push -m "wire-format-baseline" -- codependent.sty codependent-render.sty
        stashed=true
    fi
    nix develop "$PROJECT_DIR" --command bash -c "$(declare -f compile_fixtures extract_records); PROJECT_DIR='$PROJECT_DIR'; FIXTURES=(${FIXTURES[*]}); PASSES=$PASSES; compile_fixtures '$BASELINE_DIR' 'baseline'"
    if $stashed; then
        git -C "$PROJECT_DIR" stash pop
    fi
    echo "Baseline saved to $BASELINE_DIR" >&2
}

do_compare() {
    [ -d "$BASELINE_DIR" ] || die "No baseline found. Run: $0 baseline"
    echo "Compiling with working tree..." >&2
    nix develop "$PROJECT_DIR" --command bash -c "$(declare -f compile_fixtures extract_records); PROJECT_DIR='$PROJECT_DIR'; FIXTURES=(${FIXTURES[*]}); PASSES=$PASSES; compile_fixtures '$CURRENT_DIR' 'current'"

    local failed=0
    for fix in "${FIXTURES[@]}"; do
        echo "" >&2
        echo "=== $fix ===" >&2
        local base_aux="$BASELINE_DIR/$fix/$fix.aux"
        local curr_aux="$CURRENT_DIR/$fix/$fix.aux"

        if [ ! -f "$base_aux" ]; then
            echo "  SKIP: no baseline aux" >&2
            continue
        fi
        if [ ! -f "$curr_aux" ]; then
            echo "  SKIP: no current aux" >&2
            continue
        fi

        # AUX diff
        local aux_diff
        aux_diff=$(diff <(extract_records "$base_aux") <(extract_records "$curr_aux") || true)
        if [ -z "$aux_diff" ]; then
            echo "  AUX: IDENTICAL" >&2
        else
            echo "  AUX: DIFFERS" >&2
            echo "$aux_diff" >&2
            failed=1
        fi

        # CDP diff
        local base_cdp="$BASELINE_DIR/$fix/$fix.cdp"
        local curr_cdp="$CURRENT_DIR/$fix/$fix.cdp"
        if [ -f "$base_cdp" ] && [ -f "$curr_cdp" ]; then
            local cdp_diff
            cdp_diff=$(diff <(extract_cdp_records "$base_cdp") <(extract_cdp_records "$curr_cdp") || true)
            if [ -z "$cdp_diff" ]; then
                echo "  CDP: IDENTICAL" >&2
            else
                echo "  CDP: DIFFERS" >&2
                echo "$cdp_diff" >&2
                failed=1
            fi
        fi

        # PDF "Used in" count
        local base_count curr_count
        base_count=$(nix develop "$PROJECT_DIR" --command mutool draw -F text "$BASELINE_DIR/$fix/$fix.pdf" 2>/dev/null | grep -c "Used in" || echo 0)
        curr_count=$(nix develop "$PROJECT_DIR" --command mutool draw -F text "$CURRENT_DIR/$fix/$fix.pdf" 2>/dev/null | grep -c "Used in" || echo 0)
        if [ "$base_count" = "$curr_count" ]; then
            echo "  PDF 'Used in' count: $curr_count (match)" >&2
        else
            echo "  PDF 'Used in' count: baseline=$base_count current=$curr_count (MISMATCH)" >&2
            failed=1
        fi
    done

    echo "" >&2
    if [ $failed -eq 0 ]; then
        echo "RESULT: Wire format IDENTICAL across all fixtures." >&2
    else
        echo "RESULT: Wire format DIFFERS. See above." >&2
    fi
    return $failed
}

do_auto() {
    do_baseline
    do_compare
}

case "${1:-}" in
    baseline) do_baseline ;;
    compare)  do_compare ;;
    auto)     do_auto ;;
    *)        echo "Usage: $0 {baseline|compare|auto}" >&2; exit 1 ;;
esac
