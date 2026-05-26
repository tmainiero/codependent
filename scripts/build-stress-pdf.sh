#!/usr/bin/env bash
# build-stress-pdf.sh — standalone compile of stress fixtures for visual review.
#
# Unlike scripts/run-stress.sh (which goes through run-tests.py and verifies all
# TEST-PDF assertions), this script just compiles the stress .tex files using
# the package source as-is and copies the resulting PDFs into pdf-out/ with a
# user-supplied suffix.
#
# The vendored sty-theorems-ta.sty lives at testfiles/support/, which is not on
# pdflatex's default search path. The script builds a temp workdir with the
# directory layout the .latexmkrc expects, sets TEXINPUTS to reach support, and
# runs latexmk inside it.
#
# Usage:
#   scripts/build-stress-pdf.sh [SUFFIX]
#   scripts/build-stress-pdf.sh -f appendix-gray [SUFFIX]
#
# SUFFIX is appended to the PDF filename, e.g. "P04" -> stress-ta-appendix-gray-P04.pdf.
# Default suffix is empty (overwrites pdf-out/stress-ta-<variant>.pdf).
#
# Variants compiled by default: appendix-gray, inline, inline-gray.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUFFIX=""
FILTER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--filter)
            FILTER="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            SUFFIX="$1"
            shift
            ;;
    esac
done

ALL_VARIANTS=(appendix-gray inline inline-gray)
if [[ -n "$FILTER" ]]; then
    VARIANTS=("$FILTER")
else
    VARIANTS=("${ALL_VARIANTS[@]}")
fi

WORKDIR="$(mktemp -d -t codep-build-stress.XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

mkdir -p "$WORKDIR/texbuild" "$WORKDIR/pdf-out" "$WORKDIR/testfiles/compiled-examples" "$WORKDIR/testfiles/support"
cp "$REPO_ROOT/codependent.sty" "$WORKDIR/"
cp "$REPO_ROOT/codependent-render.sty" "$WORKDIR/"
cp "$REPO_ROOT/testfiles/compiled-examples/.latexmkrc" "$WORKDIR/testfiles/compiled-examples/"
cp "$REPO_ROOT"/testfiles/support/*.sty "$WORKDIR/testfiles/support/" 2>/dev/null || true

mkdir -p "$REPO_ROOT/pdf-out"

for variant in "${VARIANTS[@]}"; do
    src="$REPO_ROOT/testfiles/compiled-examples/stress-ta-${variant}.tex"
    if [[ ! -f "$src" ]]; then
        echo "build-stress-pdf: no fixture for variant '${variant}' at $src" >&2
        exit 1
    fi
    cp "$src" "$WORKDIR/testfiles/compiled-examples/"

    echo "build-stress-pdf: compiling stress-ta-${variant}..."
    (cd "$WORKDIR/testfiles/compiled-examples" && \
        nix develop "$REPO_ROOT" --command latexmk -pdf -interaction=nonstopmode "stress-ta-${variant}.tex" >/dev/null)

    if [[ -n "$SUFFIX" ]]; then
        out="$REPO_ROOT/pdf-out/stress-ta-${variant}-${SUFFIX}.pdf"
    else
        out="$REPO_ROOT/pdf-out/stress-ta-${variant}.pdf"
    fi
    cp "$WORKDIR/pdf-out/stress-ta-${variant}.pdf" "$out"
    pages=$(nix develop "$REPO_ROOT" --command qpdf --show-npages "$out" 2>/dev/null || echo "?")
    echo "build-stress-pdf: wrote $out (${pages} pages)"
done
