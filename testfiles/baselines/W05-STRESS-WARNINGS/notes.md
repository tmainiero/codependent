# W05-STRESS-WARNINGS baseline rotation notes

Captured after W05-STRESS-WARNINGS-P01 (commit 97f003a).

## Why rotated

Content edits to 3 stress fixtures to eliminate overfull \hbox warnings:

- stress-ta-inline.tex: terminology paragraph (2.4pt), backward-proof body (0.6pt),
  joint-proof body (19.7pt)
- stress-ta-inline-gray.tex: same 3 fixes (structurally parallel to inline)
- stress-ta-appendix-gray.tex: forward-proof body (13.7pt), joint-proof body (19.7pt)

Content changes alter pdf_objects_sha for all 3 stress fixtures, and cdp_sha for
all 3 (source-line metadata in the .cdp shifts with content length changes).
The appendix-gray fixture also has aux_sha change (page-count-sensitive cross-refs).

## Pre-rotation audit

Verified via `verify-wire-baseline.py --manifest .../W05-PARA-ORPHAN-FIX/baseline.sha256.json`:
- 7 mismatches, all in the expected set (stress-ta-{appendix-gray,inline,inline-gray})
- No unexpected deltas

## Post-rotation verify

`verify-wire-baseline.py --manifest .../W05-STRESS-WARNINGS/baseline.sha256.json`:
All 76 fixtures match.

## Supersedes

W05-PARA-ORPHAN-FIX (marked superseded_by in that manifest)
