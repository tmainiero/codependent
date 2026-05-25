# codependent

codependent is a LaTeX package for numbering mathematical atoms and showing where each one is used later in the document.

It also serves to help automate the production of dependency graphs (or at least referencing graphs) for mathematical results within individual papers produced using standard LaTeX macros.

## What it does

Mathematical papers often ask the reader to move in both directions: a
lemma is proved early, used much later, and then used again inside a proof
or equation. LaTeX gives you crossreferencing capabilities using `\label` and
`\ref`;
oftentimes an invocation of `\ref` is used as a "forward-reference" to a result/definition that it depends on, where *forward* here is being used in the sense of arrows in a dependency graph: arrows point from a statement *to* the result/definition that it depends on.
However, there is no automated way to see "back-references" to a given result: a collection of results where that given result is called upon.

codependent adds that missing automated crossreferencing layer. You mark theorem-like
environments as tracked, write ordinary `\label` and `\ref` commands, and run
LaTeX enough times for references to settle. The package records which
tracked atom contains each reference and then renders a small "Used in ..."
annotation at the target atom.

The intended setting is math-paper authoring: theorem statements,
definitions, proofs, paragraphs, and displayed equations. The package does
not require an external analysis tool for this basic PDF behavior; the
back-reference graph is inverted inside LaTeX using the usual `.aux` rerun
cycle.

The package is meant to be compatible with `amsthm` and `ntheorem` backends as well as `thmtools`, with pending support for `keytheorems`.
The goal is compatibility with all major LaTeX packages (within reason).

## Status

codependent is pre-release software. It has not been submitted to CTAN, and
its public API may still change before a packaged release.

For the current design history and audit trail, see
[`docs/HISTORY.md`](docs/HISTORY.md).

This README is only an entry point. It is meant to help a new reader try the
package and find the deeper design notes, not to freeze the final user manual
or CTAN documentation.

## Using
The package is not yet on CTAN, the simplest way to use it in its current state is to place the sty files: `codependent.sty` and `codependent-render.sty` in the directory of your .tex file and place `\usepackage{codependent}` in the preamble.

## Minimal example

Here is a small document that tracks the `theorem` environment and records a
reference from an adjacent proof back to the theorem.

```latex
\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}[section]
\usepackage{codependent}
\codeptrack{theorem}
\begin{document}
\section{A small example}
\begin{theorem}\label{thm:main}
Every codependent README has a minimal example.
\end{theorem}
\begin{proof}
This proof refers back to Theorem~\ref{thm:main}.
\end{proof}
\end{document}
```

After two LaTeX runs, the theorem is numbered as `Theorem 1.1`. Because the
proof refers to `thm:main`, codependent appends a small back-reference to the
theorem saying that it is used in `1.1*`. 
The star on `1.1*` is an indicator that the proof of `Theorem 1.1` is the source of the reference.

The first run may only establish labels and write graph data to the `.aux`
file. The later run has enough information to invert the graph and print the
back-reference. That is the same kind of rerun cycle LaTeX already uses for
tables of contents and ordinary cross-references.

## What's in the package

- Shared atom numbering for tracked theorem-like environments and ordinary
  paragraph atoms.
- Inline back-references that render "Used in ..." at the atom being
  referenced.
- Proof attribution, so an adjacent or explicitly attributed proof appears as
  a starred use of the theorem it proves.
- Equation tracking, so references from numbered displayed equations can show
  up as equation-number sources.
- Appendix mode, which can collect back-references into a dependency index
  instead of rendering them inline.

## Installation

For now, clone the repository and put these two files next to your `.tex`
source:

- `codependent.sty`
- `codependent-render.sty`

You can also symlink both files into your local `texmf` tree if that is how
you manage local packages. Keep the two `.sty` files together; the main package
loads the rendering layer from the companion file.

When codependent is released through CTAN, this section should gain the usual
`tlmgr install codependent` instruction.

## Build and test

Contributor conventions live in [`CLAUDE.md`](CLAUDE.md). In particular, run
the test suite through the Nix development environment:

```sh
nix develop --command python3 scripts/run-tests.py
```

That command is the project-level test entry point. The repository also has
linters and narrower test filters, but the README is not meant to replace the
contributor guide.

## Dependencies

`codependent.sty` directly declares these LaTeX package dependencies:

- `etoolbox`
- `pgfkeys`

A typical document also loads a theorem backend before codependent, usually
`amsthm` or `ntheorem`, and defines its theorem-like environments before
calling `\codeptrack{...}`.

The following packages are common companions rather than hard requirements:

- `hyperref`, for clickable links in references and back-references.
- `cleveref`, if you want `\cref`, `\Cref`, and related reference commands to
  be tracked.
- `amsmath`, if you use displayed equation environments such as `align`,
  `gather`, or `multline`.

## Credits

codependent.sty is built around a direct port of the back-reference machinery
from `dpmac.tex` by Dmitri Pavlov.

The provenance record is in [`docs/CREDITS.md`](docs/CREDITS.md), including
the upstream source URL, the recorded hash of the reviewed file, and notes on
which parts were ported, adapted, replaced, or dropped.

The package inherits its GPLv3 license from Pavlov's `dpmac` code.

## License

codependent is licensed under the GNU General Public License, version 3,
inherited from the `dpmac.tex` back-reference machinery it ports.

## Further reading

- [`docs/BEHAVIOR.md`](docs/BEHAVIOR.md) describes the testable behavior of
  the package.
- [`docs/DESIGN.md`](docs/DESIGN.md) explains the architecture and how the
  LaTeX-side back-reference graph works.
- [`docs/COOKBOOK.md`](docs/COOKBOOK.md) contains worked notes for custom
  placement of `\codepbackrefs`.
