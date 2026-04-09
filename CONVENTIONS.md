# semtex.sty Code Conventions

These conventions are mandatory for all code in `semtex.sty`.
The goal is CTAN-publishable quality.

## Naming

- **Internal macros**: `\semtex@name`. Always `@`-guarded.
  Never leak into the user namespace.
- **Public macros**: `\semtex` prefix or short documented names
  (e.g., `\atomlabel`, `\backrefinline`). Minimal public API.
- **Counters**: `semtex@atom`, `semtex@section`, etc.
  User-visible counter name: `atom`.
- **Booleans**: `\ifsemtex@backrefs`, `\ifsemtex@appendix`, etc.
- **Lengths/skips**: `\semtex@backrefskip`, etc.
- **Token registers**: `\semtex@toks@...`
- **Key-value keys**: all under the `/semtex/` family.

## Structure

The `.sty` file follows this section order:

```
1. Identification (\ProvidesPackage, date, version, description)
2. Required packages (\RequirePackage)
3. Options (pgfkeys or kvoptions, \ProcessOptions)
4. Internal state (counters, booleans, registers)
5. Core numbering machinery
6. Theorem environment hooks (thmtools integration)
7. Paragraph numbering (\AddToHook{para/begin})
8. Back-reference display (inline + appendix modes)
9. Data file I/O (reading semtex-generated .backrefs.tex)
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
  with thorough comments.

## Error handling

- Use `\PackageError{semtex}{message}{help}` for fatal errors.
- Use `\PackageWarning{semtex}{message}` for non-fatal issues.
- Use `\PackageInfo{semtex}{message}` for diagnostics.
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
- Required: `etoolbox`, `thmtools`, `pgfkeys`.
- Optional (detected at load): `hyperref`.
- Do NOT require `amsthm` or `ntheorem` directly.
  `thmtools` abstracts this. Detect which backend is loaded.

## Compatibility

- Target LaTeX kernel October 2020+ (for `\AddToHook`).
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

- **latexindent** — formatter. Run `latexindent -w semtex.sty`
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

- Provide a minimal test document (`test-semtex.tex`) that
  exercises all features.
- Test with and without hyperref loaded.
- Test with both amsthm and ntheorem backends.
- Test the three backrefs modes (inline, appendix, none).
- Test edge cases: empty sections, atoms with no back-refs,
  atoms referenced 10+ times.

## What NOT to do

- Do not use `\everypar` directly. Use `\AddToHook{para/begin}`.
- Do not hardcode font sizes. Use relative commands (`\small`,
  `\footnotesize`) or length parameters.
- Do not define theorem environments. Hook into `thmtools`.
- Do not handle math rendering. That is the preamble's job.
- Do not assume a specific numbering depth (some documents
  may not use subsections).
