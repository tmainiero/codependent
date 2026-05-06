# codependent.sty Code Conventions

These conventions are mandatory for all code in `codependent.sty`.
The goal is CTAN-publishable quality.

## Naming

- **Internal macros**: `\codep@name`. Always `@`-guarded.
  Never leak into the user namespace.
- **Public macros**: `\codep` prefix or short documented names
  (e.g., `\codeptrack`, `\codepsuppress`). Minimal public API.
- **Counters**: user-visible counter is `atom`.  Internal
  counters use `\codep@nestlevel`, etc.
- **Booleans**: `\ifcodep@backrefs`, `\ifcodep@appendix`, etc.
- **Lengths/skips**: `\codep@backrefskip`, etc.
- **Token registers**: `\codep@toks@...`
- **Key-value keys**: all under the `/codep/` family.

## Structure

The `.sty` file follows this section order:

```
1. Identification (\ProvidesPackage, date, version, description)
2. Required packages (\RequirePackage)
3. Options (pgfkeys, \ProcessOptions)
4. Internal state (counters, booleans, registers)
5. Core numbering machinery
6. Theorem environment hooks (etoolbox patching)
7. Paragraph numbering (\AddToHook{para/begin})
8. Back-reference emission (\AddToHook{para/end})
9. Data file I/O (reading .sbr file)
10. User-facing API
11. Compatibility guards and warnings
```

Each section separated by a comment block:

```tex
%% ===================================================================
%% Section N: Title
%% ===================================================================
```

## Documentation

- Every public macro gets a comment block:
  ```tex
  % \macroname{arg1}{arg2}
  %   Brief description of what it does.
  %   arg1 -- what arg1 is
  %   arg2 -- what arg2 is
  ```
- Internal macros: one-line comment above explaining purpose.
- No commented-out dead code. Delete it or don't write it.
- Eventually target dtx format, but start as a clean .sty
  with thorough comments.  dtx is a pre-submission
  requirement for CTAN.

## Error handling

- Use `\PackageError{codependent}{message}{help}` for fatal errors.
- Use `\PackageWarning{codependent}{message}` for non-fatal issues.
- Use `\PackageInfo{codependent}{message}` for diagnostics.
- Never `\errmessage` or `\message` directly.
- Guard optional features:
  ```tex
  \@ifpackageloaded{hyperref}{%
    ... hyperref-aware code ...
  }{%
    ... fallback ...
  }
  ```

## Dependencies

- `\RequirePackage` only. Never `\usepackage` inside a .sty.
- Required: `etoolbox`, `pgfkeys`.
- Optional (detected at load): `hyperref`.
- Do NOT require `amsthm`, `ntheorem`, or `thmtools`.
  Hook into theorem environments by name via `etoolbox`,
  regardless of which backend defines them.

## Compatibility

- Target LaTeX kernel TeX Live 2021+ (stable `\AddToHook`,
  including `para/begin`, `para/end`, `para/after`).
- Test with `article`, `book`, `report` document classes.
- Do not assume any particular font setup.
- Do not redefine standard LaTeX commands unless absolutely
  necessary, and always document why.

## Style

- Indent with 2 spaces (no tabs). This is the l3build /
  LaTeX Project convention.
- No trailing whitespace.
- Lines under 80 characters. Hard limit 100.
- Use `%` at end of lines to prevent spurious spaces —
  every line inside a macro definition that doesn't
  intentionally produce a space must end with `%`.
- Prefer `\newcommand` over `\def` for public macros.
  Use `\def` only when LaTeX's argument parsing is insufficient.
- Prefer `\csname ... \endcsname` patterns over
  `\expandafter` chains when possible.
- Brace all macro arguments: `\foo{bar}` not `\foo bar`.
- `\begin`/`\end` on their own lines, contents indented.
- Space after commas, not before punctuation.

## Tooling

All of these must pass before code is considered done.

- **latexindent** — formatter. Run `latexindent -w codependent.sty`
  with a project `.latexindent.yaml` enforcing 2-space indent.
  Agents must not hand-format when the tool exists. Pure
  structural tool — works fine on .sty internals.
- **l3build** — build and regression test framework. Designed
  for package development; expects .sty internals. Use for:
  - `l3build check` — run regression tests (.lvt files)
  - `l3build doc` — build documentation
  - `l3build ctan` — package for CTAN submission
- **ChkTeX** — semantic linter. Run on **test documents**,
  not on the .sty itself. ChkTeX assumes document-level LaTeX
  and will false-positive on `\def`, `\expandafter`, catcode
  tricks, etc. that are normal inside a package. Configure
  `.chktexrc` to suppress inapplicable warnings, with a
  comment documenting each suppression.
- **lacheck** — same as ChkTeX: run on test documents only,
  not the .sty.

All tools available in nixpkgs via TeX Live.

## Testing

Use l3build regression tests (.lvt files).  See DESIGN.md
for the full test file list.  At minimum:

- Test with and without hyperref loaded.
- Test with both amsthm and ntheorem backends.
- Test the three backrefs modes (inline, appendix, none).
- Test all depth settings (1, 2, 3).
- Test edge cases: empty sections, atoms with no back-refs,
  atoms referenced 10+ times, nested tracked environments.

## What NOT to do

- Do not use `\everypar` directly. Use `\AddToHook{para/begin}`.
- Do not patch `\par` directly. Use `\AddToHook{para/end}`.
- Do not hardcode font sizes. Use relative commands (`\small`,
  `\footnotesize`) or length parameters.
- Do not define theorem environments. Hook via `etoolbox`.
- Do not handle math rendering. That is the preamble's job.
- Do not assume a specific numbering depth (some documents
  may not use subsections).

## Behavioral Traceability (mandatory)

Every top-level macro definition in `.sty` files MUST have exactly
one classification tag in the `%%` comment block immediately above it.

### Tag types

```tex
%% @behavior B-XXX-YYY
\def\codep@macroname{...}
```
This macro directly implements behavioral statement `[B-XXX-YYY]`
from `BEHAVIOR.md`. Multiple `@behavior` tags allowed (one macro
may implement several behaviors).

```tex
%% @implements \codep@parentmacro
\def\codep@helpername{...}
```
This macro is a helper for `\codep@parentmacro`, which must itself
have `@behavior` tags. Use this for decomposed helpers that serve
one parent.

```tex
%% @utility
\def\codep@purelibrary{...}
```
Pure internal plumbing with no behavioral decisions. If a utility
starts making behavioral choices (checking options, branching on
atom type, etc.), it must be promoted to `@behavior` or split.

### Rules

- **No unclassified macros.** The traceability linter
  (`lint_traceability.py`) rejects any new macro without a tag.
  Pre-existing unclassified macros are listed in
  `.traceability-baseline` and must be classified during the
  Phase 3 rewrite.
- **No macro may have both `@behavior` and `@implements`.**
  It is either a contract holder or a helper, not both.
- **Every `@behavior` ID must exist in `BEHAVIOR.md`.**
  Stale or invented IDs are errors.
- **Every `@implements` target must have `@behavior` tags.**
  Orphan helpers are errors.
- **Baseline can only shrink, never grow.** Classifying a
  baselined macro requires removing it from the baseline.

### Verification

```sh
python3 .claude/scripts/lint_traceability.py          # full check
python3 .claude/scripts/lint_traceability.py --update-baseline  # regenerate
```

The linter runs automatically via PostToolUse (on .sty edits) and
PreCommit hooks.

## Stress Test

The canonical stress fixture is `testfiles/compiled-examples/stress-ta-appendix-gray.tex`. It is the integration ground truth and also a visual contract.

Retained LIVE stress fixtures:

- `stress-ta-appendix-gray.tex` — appendix mode, gray backrefs, and non-default appendix page-number format.
- `stress-ta-inline.tex` — plain/default-color inline rendering path.
- `stress-ta-inline-gray.tex` — inline rendering path with gray backrefs.

### Non-default override sentinels

Any `\codepsetup` value in `testfiles/compiled-examples/stress-ta-appendix-gray.tex` that deviates from the package default MUST:
1. Carry an inline `%%NONDEFAULT-OVERRIDE%%` sentinel on the line of the override.
2. Be listed in the `%% Active non-default overrides:` block at the top of the fixture.

Rationale: the stress fixture is also a visual contract. When a renderer regression appears, a reviewer must be able to distinguish "package default behavior changed" from "fixture is exercising a non-default code path". The sentinel + index block make this distinguishable without searching `git log`.

## Build output location

Manual LaTeX compiles MUST route output into `texbuild/` (aux/log/intermediates) and `pdf-out/` (PDFs). This matches the project `.latexmkrc` and the user's vimtex config.

- **latexmk** (preferred): plain `latexmk foo.tex` — `.latexmkrc` handles the dirs.
- **pdflatex direct**: `pdflatex -output-directory=texbuild foo.tex`, then `mv texbuild/foo.pdf pdf-out/`.
- **If artifacts end up in the repo root anyway**: run `scripts/clean-build.sh` to relocate them (or `--purge` to delete).

`texbuild/` and `pdf-out/` are gitignored. The test runner uses tempdirs and is unaffected.
