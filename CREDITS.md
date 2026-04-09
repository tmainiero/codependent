# Credits and Provenance

## Main credit

`semtex.sty` is built around a direct port of the
back-reference machinery from **`dpmac.tex`** by
**Dmitri Pavlov**.

- Author: Dmitri Pavlov
- Source: <https://dmitripavlov.org/tex/dpmac.tex>
- Format: Plain TeX (~1900 lines, ~75 KB)
- License: **GNU General Public License, version 3**
- Copyright notice on the upstream file:
  `Copyright 2017, 2018 Dmitri Pavlov` (file header);
  the UTF-8 block carries `Copyright 2008, 2015, 2018`.
- Fetched from: same URL, during the architecture review
  recorded under `tools/semtex-cli/reviews/`.

The SHA-256 of the upstream file fetched during review
**must be recorded here before committing the ported
code**.  Per REVIEW_D finding #10 the placeholder values
below are explicitly marked `UNPINNED` so a future grep
will catch them.

```
UNPINNED: fetch date    TBD (ISO 8601, e.g. 2026-04-12)
UNPINNED: dpmac.tex SHA-256    TBD (64-char lowercase hex)
UNPINNED: dpmac.tex line count TBD (`wc -l`)
UNPINNED: dpmac.tex byte count TBD (`wc -c`)
```

### Pre-commit checklist for the dpmac port

Before the first commit that includes ported code:

1. Fetch the canonical dpmac source:
   ```
   curl -fsSL https://dmitripavlov.org/tex/dpmac.tex \
     -o /tmp/dpmac.tex
   ```
2. Record the SHA-256:
   ```
   sha256sum /tmp/dpmac.tex
   ```
3. Record the wall-clock fetch date in ISO 8601 format
   (UTC, day precision is fine).
4. Record `wc -l` and `wc -c` so a future drift check
   can be done without re-fetching.
5. Replace every `UNPINNED:` line above with the actual
   value.  Verify with `grep -n UNPINNED CREDITS.md`
   that all four are gone.
6. Reference the pinned hash in `DESIGN.md` Section 8a's
   "License note" subsection so the source-of-truth lives
   in two places (CREDITS.md as the canonical record,
   DESIGN.md as a cross-reference for the implementer).

Why this matters: a "we ported about 60 lines from
dpmac" claim is hard to audit without knowing **which
60 lines from which version**.  Pinning the hash and
date converts a vague provenance claim into a
reproducible one.

See REVIEW_C finding #14 and REVIEW_D finding #10 for
the rationale and the original critic discussion.

## What was ported

### Bucket A — verbatim (rename to `\semtex@*`)

Adapted from dpmac's back-reference subset (lines
~1000-1088 of `dpmac.tex`).  The structure and control
flow of the following macros are derived directly from
Pavlov's code; only the namespace changes and the LaTeX
hook system replaces the Plain TeX `\everypar` / `\par`
wiring.

| dpmac (Plain TeX) | semtex.sty | Role |
|---|---|---|
| `\newtoks\backreflist` | csname linked list `semtex@brq@*` | Defer queue (restructured — see Bucket B) |
| `\def\predefbackref` | `\semtex@predefbr` (optional init) | Pre-initialise target list |
| `\def\recordbackref` | `\semtex@recordbr` | Enqueue at reference time |
| `\def\processbackref` | `\semtex@processbr` | Graph inversion step |
| `\newtoks\atendbr` | `\semtex@pendingbr` | Per-atom pending back-ref text |
| `\def\nextpar` / `\finishpar` (flush segments) | `\semtex@flushbackref` (via `para/end` hook) | Flush at atom end |
| `\newif\ifaddbr` | `\ifsemtex@addbr` (consecutive-dup gate) | Internal gate |

### Bucket B — adapted

The *algorithm* is Pavlov's; the *implementation* diverges
in response to the adversarial review (`REVIEW_C`) and to
LaTeX's hook system:

- The defer queue is a **csname linked list** rather than
  a token register.  The token-register pattern Pavlov
  uses is O(N^2) at 15k refs; the linked list is O(1) per
  append and O(N) per flush.  Per REVIEW_C finding #2.
- The per-target back-ref list is also a linked list, not
  a single `\gdef`-ed macro, to avoid O(K^2) per target.
  Per REVIEW_C finding #11.
- The `\newlabel` override is installed at
  `\AtEndPreamble` (not `\AtBeginDocument`) with an
  explicit `\DeclareHookRule` ordering constraint.  Per
  REVIEW_C finding #3.  This is LaTeX-specific; dpmac
  does not have this concern.
- Cleveref's `@cref`-suffixed records are filtered out of
  the `\newlabel` override, per REVIEW_C finding #12.
- `\semtex@currentatom` is cleared at atom-end hooks to
  fix the stale-state bug.  Per REVIEW_A finding #3 and
  REVIEW_C finding #4.  Dpmac does not have this bug
  because its atom model and flush timing are different.
- The `.aux` rerun replaces dpmac's explicit two-pass
  driver (`\preprocess\jobname` + `\input\jobname`).
  LaTeX's own `.aux` file is used as the inter-pass
  persistence layer, so the second read of the source is
  a normal pdflatex rerun rather than an in-memory
  re-`\input`.

### Bucket C — replaced by LaTeX primitives

The following dpmac machinery is **not** ported; LaTeX
provides the functionality natively:

- `\def\preprocess` / `\def\labelaux` / `\def\processoneline`
  — dpmac's hand-rolled aux reader.  Replaced by LaTeX's
  built-in `\@input{\jobname.aux}`.
- `\hinitlabelcommand` / `\pinitlabelcommand` — dpmac's
  label-macro installer.  Replaced by LaTeX's `\label` /
  `\@newl@bel` / `\@setref` chain (patched once in
  `semtex.sty`).
- `\everypar{\numpar}` — replaced by `\AddToHook{para/begin}`.
- `\def\par{\finishpar}` — replaced by
  `\AddToHook{para/end}`.

### Bucket D — dropped

Out-of-scope dpmac features not ported:

- UTF-8 input handling (dpmac is Plain TeX; LaTeX has
  `inputenc` / native UTF-8 on modern engines).
- METAPOST embedding, TikZ-like diagram drawing.
- Bibliography management (`\tbib` / `\verifybib`).
- Unused-label verification (`\verifyref` / `\verifylabel`).
- The two-pass `\output` dummying.
- `\plabel` proofreading macros.

## Why GPLv3 applies to the whole `.sty`

The ported code (Bucket A + B) is a non-trivial subset of
the original `dpmac.tex` and carries its own copyright.
Because it is distributed as part of `semtex.sty` (a
single file), the GPL's combined-work clause applies to
the whole file.  `semtex.sty` is therefore licensed under
**GNU GPL version 3**.

The LaTeXML binding `semtex.ltxml` is an accompanying file
in the same package and is also distributed under GPLv3.

Downstream consumers who embed `semtex.sty` in larger
works inherit GPLv3 obligations (source availability,
license notice).  For a research-math documentation tool
this is the intended audience; users building
proprietary-TeX pipelines should be aware.

## Intent to reach out to Pavlov

Per user decision 2026-04-09, the project will reach out
to Dmitri Pavlov about an optional **LPPL 1.3c
dual-license courtesy** for `semtex.sty`.  LPPL is the
CTAN-standard package license and dual-licensing would
widen compatibility with TeX Live / MiKTeX distribution
conventions.  The port cannot adopt LPPL unilaterally
because the ported code is Pavlov's, so explicit consent
is required.

If Pavlov agrees, `semtex.sty` will ship under
**GPLv3 OR LPPL 1.3c** at the user's choice.  If he
declines or does not respond, GPLv3 remains the sole
license and we retain the copyleft-forward defaults.

Contact: per the UTF-8 block of `dpmac.tex`,
`pavlov` at `math.berkeley.edu` (verify the current
address before sending).

## Review history

The architecture of this package went through three
rounds of adversarial review before settling:

1. `tools/semtex-cli/reviews/REVIEW_A_correctness.md` —
   attacked the original Haskell-CLI-based design; 15
   findings, 1 blocker, 6 majors.
2. `tools/semtex-cli/reviews/REVIEW_ARCH_dpmac_port.md` —
   proposed the dpmac port; 1161 lines; answered Q1-Q10
   on feasibility and performance.
3. `tools/semtex-cli/reviews/REVIEW_C_port_proposal.md` —
   attacked the port proposal's concrete TeX code; 14
   findings, 3 blockers, 4 majors.  All fixes incorporated
   into `DESIGN.md` Section 8a.

The reviews are archived verbatim; they are not the
living design but they are the audit trail.

## License text pointer

This file is part of a package distributed under **GNU
General Public License version 3**.  The canonical license
text is at <https://www.gnu.org/licenses/gpl-3.0.txt>.
