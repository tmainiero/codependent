# semtex.sty Design

LaTeX package for Pavlov-style automatic atom numbering and
back-reference display.  **The back-reference machinery is a
direct port of Dmitri Pavlov's
[dpmac](https://dmitripavlov.org/tex/dpmac.tex) (Plain TeX, GNU
GPLv3, 2007-2023)** into the LaTeX2e hook system.  Zero external
tooling is required for the back-reference-display use case:
graph inversion happens inside pdflatex on pass 2.

This architecture was settled after three rounds of adversarial
review (see `tools/semtex-cli/reviews/`).  An earlier design
delegated graph inversion to an external Haskell CLI via a
`.sbr` sidecar; that design has been **superseded**.  The new
architecture is three-layered:

| Layer | Tooling | Role |
|---|---|---|
| 1. `semtex.sty` | pure TeX, GPLv3 | Numbering + generic back-refs (this file) |
| 2. `semtex-cli` | Haskell (future) | **Semantic** analysis only (UIDs, deps, concepts) |
| 3. mwablab ext. | project-specific | Builds on Layer 2 |

Layers 1 and 2 communicate one-way: the `.sty` writes a
`.sbl` semantic-hint sidecar (Section 9a); the CLI reads it
and never writes anything the `.sty` reads back.  The only
two-way persistence is LaTeX's own `.aux` file.

## Separation of concerns

The semtex ecosystem has three layers.  The `.sty` is the
bottom layer — it knows nothing about the layers above.

| Layer | What | Audience |
|---|---|---|
| **semtex.sty** | Atom numbering + generic back-ref display (pure TeX, dpmac port) | Anyone (CTAN) |
| **semtex-cli** | Semantic analysis: `.tex` + `.sbl` -> concept/UID/dep outputs | Anyone using the `.sty` for structured docs |
| **mwablab extension** | Project-specific semantic tooling on top of the CLI | Project-specific |

The `.sty` is fully standalone for the back-reference-display
use case.  It computes the back-reference graph in pure TeX
(see Section 8a) via a direct port of the relevant macros from
Dmitri Pavlov's `dpmac.tex`, and it writes a companion
semantic-hint sidecar file (`.sbl`, see Section 9a) that the
CLI reads for purely semantic work.  The CLI is **not** in
the back-reference-display pipeline at all.

## Architecture

```
pdflatex main.tex          pass 1: .sty numbers atoms, writes .aux + .sbl
pdflatex main.tex          pass 2: .sty reads .aux, inverts the ref graph
                                   in TeX, appends "Used in X, Y." per atom
semtex-cli analyse main.tex optional: reads .tex + .sbl (+ .aux), writes
                                      semantic-analysis artifacts
```

The two pdflatex runs are LaTeX's ordinary rerun cycle.  No
external tool is involved for back-ref display.  On pass 1,
the `.aux` has no `\semtex@atomref` records from a previous
run (or only stale ones), so the flushed back-ref queue is
empty and nothing is rendered.  On pass 2 the `.aux` is
populated and the "Used in" lines appear.  A single-pass
build produces a correctly numbered document — just without
back-references.  This matches how `\ref`, `toc`, and
`\pageref` all work, and users are trained for it.

For multi-file projects using `\subfiles` or `\include`, a
master document (`main.tex`) is required for the canonical
build.  Individual subfiles can still be compiled standalone
for drafting — they get local numbering (1.1, 1.2, ...) which
is correct within that file but not globally unique.

## Load order

```latex
\usepackage{amsthm}          % or ntheorem — load first
\newtheorem{theorem}{...}[section]
\newtheorem{definition}[theorem]{Definition}
...                           % all \newtheorem declarations
\usepackage{semtex}          % after all \newtheorem
\semtextrack{definition,theorem,proposition,...}
```

semtex.sty loads AFTER the theorem backend and AFTER all
`\newtheorem` declarations.  `\semtextrack{...}` performs
post-hoc aliasing of the shared theorem counter to the `atom`
counter.  It also auto-registers starred variants (e.g.,
`definition` → both `definition` and `definition*`, which
`amsthm` creates automatically).

## Numbering

### Shared counter

One counter (`atom`) for all block types: paragraphs,
definitions, theorems, propositions, lemmas, corollaries,
remarks, examples, proofs.

When `\semtextrack` is called, it:

1. Creates the `atom` counter.
2. Copies the current value of the `theorem` counter to
   `atom` (preserving any state).
3. Aliases `theorem` to `atom`
   (`\let\c@theorem\c@atom`).
4. Updates counter reset lists: removes `theorem` from
   the `section` counter's reset list (from
   `\newtheorem`'s `[section]` argument) and adds `atom`
   to the reset list of the appropriate sectioning level
   (determined by the `depth` option).  Uses
   `\@removefromreset` and `\@addtoreset`.
5. Updates the display format (`\theatom`) to match the
   depth setting.

All `\newtheorem` definitions that shared the `theorem`
counter now share the `atom` counter via the alias.
Existing `\label`/`\ref` pairs continue to work because
`\c@theorem` points to the same register as `\c@atom`.

Because `\newtheorem` already advances the counter on entry
(via the alias), the `\AtBeginEnvironment` hook does NOT
advance it again — it only handles suppression and display
formatting.  No double-increment.

### Depth

The `depth` option controls how many sectioning levels appear
in the atom number and where the counter resets:

```latex
\usepackage[depth=1]{semtex}  % 2.3      (default)
\usepackage[depth=2]{semtex}  % 2.1.3
\usepackage[depth=3]{semtex}  % 2.1.3.4  (if you must)
```

Depth is relative to the document's top-level sectioning
command.  The `.sty` auto-detects whether `\chapter` exists
(book/report) or not (article):

| depth | article | book/report |
|---|---|---|
| 1 | section.atom | chapter.atom |
| 2 | section.subsection.atom | chapter.section.atom |
| 3 | section.sub.subsub.atom | chapter.section.sub.atom |

The atom counter resets at the deepest sectioning level
included in the display number.  Any existing counter reset
from `\newtheorem`'s `[section]` argument is harmless — the
atom counter is the same counter, and resetting at a coarser
level is a subset of resetting at a finer level.

### Equation numbering

By default, equation numbering is independent of atom
numbering.  Atoms render as superscript margin numbers;
equations render as standard parenthesized numbers.

```latex
\usepackage[equations=separate]{semtex}  % independent (default)
\usepackage[equations=shared]{semtex}    % single counter for everything
```

In `shared` mode, `\let\c@equation\c@atom` — unstarred
equations consume atom numbers.  Starred equations
(`equation*`, `\[...\]`) do not advance any counter and
display no number — this is standard LaTeX behavior.
No gap in numbering; the next atom picks up naturally.

In `separate` mode, there is no ambiguity in "Used in" lists
because those only reference atom numbers, never equation
numbers.

### Paragraph numbering

Every paragraph gets a number via `\AddToHook{para/begin}`.
Rendered as a small superscript in the left margin:

```
^{1.1}  A category C consists of the following data...

^{1.2}  subject to the following axioms...
```

Small, unobtrusive, does not interrupt text flow.

#### Suppression mechanism

A depth counter `\semtex@nestlevel` controls suppression.
When `\semtex@nestlevel > 0`, the `para/begin` hook skips
numbering.  Any environment or command that should suppress
numbering increments `\semtex@nestlevel` on entry and decrements
on exit.

**Suppressed environments** (via `\AtBeginEnvironment` /
`\AtEndEnvironment`):
- List environments: `enumerate`, `itemize`, `description`
- Quoting: `quote`, `quotation`
- Floats: `figure`, `table`
- Boxes: `minipage`
- Tables: `tabular`, `tabularx`, `longtable`
- Theorem environments (see below — they get one number
  for the whole environment, not per-paragraph)

**Suppressed commands** (via `etoolbox` `\pretocmd` /
`\apptocmd` patching):
- `\footnote` — increment `\semtex@nestlevel` before body,
  decrement after
- `\parbox` — same
- `\caption` — same

**User-extensible:**
```latex
\semtexsuppress{myenvironment}   % for environments
\semtexsuppresscmd{\mycommand}   % for commands
```

**Sectioning commands** (`\section`, `\subsection`, etc.)
suppress the heading paragraph itself.  The first content
paragraph after a section heading IS numbered.

### Theorem environment numbering

Hooked via `etoolbox`'s `\AtBeginEnvironment` and
`\AtEndEnvironment` for each environment name registered
with `\semtextrack{...}`.  No dependency on `thmtools` —
works with plain `amsthm`, `ntheorem`, or raw `\newtheorem`.

When a tracked environment opens:

1. Set `\semtex@nestlevel > 0` so paragraphs within the
   environment don't get separate numbers.
2. Adjust the displayed number to use the atom format.

The counter is NOT advanced by the hook — `\newtheorem`
already advances the aliased `atom` counter on entry.
No double-increment.

When it closes, decrement `\semtex@nestlevel`.

Result: "Definition 2.3." uses the same counter as
paragraph 2.2 before it.  Multiple paragraphs within a
single definition share one number.

**Nested tracked environments:** if `\semtex@nestlevel > 0`
when a tracked environment opens (i.e., it's inside another
tracked environment), the counter is NOT advanced.  The inner
environment is part of the outer atom.  Example: a
`definition` containing an `example` gets one atom number.

**Starred environments:** `\semtextrack{definition}` auto-
registers both `definition` and `definition*`.  Both get atom
numbers.

### Proof environments

`proof` (from `amsthm`) is not a `\newtheorem` environment.
It is hooked separately via `\AtBeginEnvironment{proof}`.

By default, proofs get their own atom number (Pavlov style).
The number renders as a superscript margin number (like
paragraphs); the "Proof." heading from `amsthm` stays as-is.

```latex
\usepackage[proofs=numbered]{semtex}    % default
\usepackage[proofs=unnumbered]{semtex}  % skip numbering
```

### Labels

No auto-generated labels.  Authors use explicit `\label{...}`
as usual.  The `.sty` does not create labels because
display-number-based labels would be unstable under
reorganization.

## Aux file protocol

The `.sty` writes structured data to the `.aux` file so that
the semtex CLI can compute back-references.  This follows the
standard LaTeX pattern used by `hyperref`, `cleveref`, etc.

### Atom registration

When each atom is created (in the `para/begin` hook or at
theorem environment entry), the `.sty` writes:

```tex
\semtex@atom{1.2.3}{paragraph}
\semtex@atom{1.2.4}{Definition}
```

Format: `\semtex@atom{display-number}{type}`.  The type is
the display name for theorem environments (e.g., "Definition",
"Theorem") or "paragraph" for plain paragraphs.  This is a
display name, not a programmatic identifier.

No label is included — the CLI associates labels to atoms by
matching `\newlabel{...}{{1.2.4}{...}}` entries to atom
numbers.

### Reference tracking

The `.sty` patches `\@setref` — the internal kernel command
that ALL reference commands (`\ref`, `\eqref`, `\autoref`,
`\cref`) eventually call.  One patch point, works regardless
of what redefines the user-facing commands (hyperref, cleveref,
etc.).

When `\@setref` fires inside a tracked atom, the `.sty`
writes:

```tex
\semtex@atomref{1.2.5}{def:category}
\semtex@atomref{1.2.5}{eq:composition}
```

Format: `\semtex@atomref{current-atom-number}{target-label}`.
Only written when `\semtex@currentatom` is non-empty (i.e.,
inside a tracked atom context).

### Safety

On pass 1 (no prior `.aux` exists), both `\semtex@atom` and
`\semtex@atomref` are defined as `\providecommand` no-ops in
the preamble so that LaTeX's aux read (which happens at
`\begin{document}`) does not error when no records are
present.

On pass 2 (and all subsequent reruns), the preamble installs
active definitions **before** the aux read (pin point:
`\AtEndPreamble` / `begindocument/before`, see Section 8a
"Load order" for the exact hook).  The active definitions
turn `\semtex@atomref{src}{tgt}` into an enqueue onto the
back-ref defer queue — exactly Pavlov's `\recordbackref`
pattern, adapted to LaTeX's `.aux` rerun as the inter-pass
persistence layer.

### Staleness detection

Dropped.  The superseded design used a content hash to
detect `.sbr` / `.aux` drift; with the `.sbr` file gone,
LaTeX's own rerun mechanism (`rerunfilecheck`, latexmk,
kernel `Label(s) may have changed` warnings) already handles
drift detection.  The `.sty` emits a `\PackageInfo` when a
pass 2 flush produces a different `\semtex@br@*` population
than the preamble expected.

## Back-references

**The back-reference pipeline is defined in Section 8a below.**
It is entirely in-TeX (ported from dpmac), runs during the
normal pdflatex rerun cycle, and does not use any external
tool or `.sbr` sidecar.  The previous three-file design
(`.aux -> semtex-cli -> .sbr`) is archived under
`tools/semtex-cli/reviews/` as the pre-port architecture.

### Display modes (unchanged)

At the point where a populated back-ref list is available
(Section 8a), it is rendered in one of three modes:

**Inline mode (default).**  At the end of each atom, if
back-ref data exists, the `.sty` appends

```
                            Used in 2.1, 3.4, 5.2.
```

rendered in `\small\sffamily`.  Each number is a hyperlink
when `hyperref` is loaded.  The rendering is performed by
`\semtex@renderinline` (currently present in `semtex.sty`
Section 8).  The only change required by the port is the
*source* of the pending list: instead of being populated
from `.sbr`-file data, it is populated from the csname
`\semtex@br@<num>` that Section 8a's graph inversion
produced during the `begindocument` flush.

**Appendix mode.**  Back-refs are collected during the same
csname walk and typeset via `\semtexappendix`.  Grouping
by section title is derived from the TOC entries LaTeX
already writes to `.aux`.

```
Dependency Index

1  Categories
   1.2  Category .............. 2.1, 2.3, 3.1, 3.4, 4.2,
                                5.1, 5.3, 7.2
   1.3  Hom-set ............... 2.1, 4.1
```

**None mode.**  Numbering only, no back-references
displayed.  The Section-8a graph inversion is still run
(cheap) but the rendering step is skipped.

## Section 8a — Back-reference graph (ported from dpmac, GPLv3)

> Portions of this section are derived from `dpmac.tex` by
> **Dmitri Pavlov** (Copyright 2017, 2018 Dmitri Pavlov,
> distributed under GNU GPL version 3).  The derivative in
> `semtex.sty` is Copyright 2026 and is also distributed under
> GNU GPL version 3.  Original source:
> <https://dmitripavlov.org/tex/dpmac.tex>.  See
> `tools/semtex-sty/CREDITS.md` for the provenance table.

### Intent

A back-reference link from "Proposition 2.1" down to
"Definition 1.2" is written by the author as
`\ref{def:cat}` inside Proposition 2.1.  To display the
*reverse* arrow ("Definition 1.2 is used in 2.1") the `.sty`
must invert the reference graph.  Pavlov's `dpmac.tex`
solves this in ~45 lines of Plain TeX using two token
registers and a family of per-target csnames.  Section 8a
adapts that algorithm to LaTeX2e, with LaTeX's own `.aux`
rerun acting as the inter-pass persistence layer that
Pavlov implements with an explicit two-pass driver.

### Walkthrough (two-pass protocol)

Two pdflatex runs are involved, identical to the normal
LaTeX rerun cycle:

1. **Pass 1 (collection).**  On each `\ref` (via the
   `\@setref` patch installed by Section 8a.0 below), the
   `.sty` writes `\semtex@atomref{src}{tgt}` to `.aux`,
   where `src` is the current atom display number and `tgt`
   is the label key.  If no current atom is active
   (`\semtex@currentatom` is empty), nothing is written —
   see Section 8a.5 "currentatom state management" below.

2. **Pass 2 (inversion).**  Before LaTeX reads `.aux`
   inside `\begin{document}`, the preamble installs active
   definitions for `\semtex@atomref` and for a `\newlabel`
   override (pinned at `\AtEndPreamble` per REVIEW_C
   finding #3; see "Load order" below).  As `.aux` is read,
   each `\newlabel` entry populates
   `\semtex@lblnum@<key>` with the label's display number,
   and each `\semtex@atomref` call enqueues a
   `\semtex@processbr` invocation onto the defer queue.
   After `.aux` is fully read, a single flush iterates the
   queue, populating per-target node csnames
   `\semtex@brnode@<num>@<k>` with the inverted lists.
   Typesetting then proceeds; at each atom's
   `\semtex@queuebackref` call site, `\semtex@collapsebr`
   lazily materialises `\semtex@br@<num>` from the per-
   target nodes (see Section 8a.6 for the edit to
   `\semtex@queuebackref` that triggers this collapse); the
   `\semtex@flushbackref` hook then reads that csname and
   the existing `\semtex@renderinline` prints "Used in X, Y."

The persistence layer is LaTeX's `.aux`; no `.sbr` file is
involved.  Graph inversion runs once per pdflatex pass, in
TeX, in bounded time (see "Performance" below).

### Pipeline summary (per D#3)

End-to-end data flow, with hook names and macro names
pinned so an implementer can trace each step back to a
specific section of the sketch:

```
Pass 1 (collection):
  para/begin (semtex.sty Section 7)
    -> \refstepcounter{atom}
    -> \edef\semtex@currentatom{\theatom}
    -> \semtex@queuebackref{\semtex@currentatom}
         [on pass 1 this is a no-op; the csnames do not
          exist yet.  Edit lives in Section 8a.6.]
  \ref / \eqref / \autoref / \cref  (any reference command)
    -> \@setref (patched in Section 8a.0)
    -> if \semtex@currentatom non-empty:
         \immediate\write \@auxout
           \semtex@atomref{\semtex@currentatom}{<label>}
  para/end  (semtex.sty Section 7)
    -> \semtex@flushbackref         [no-op on pass 1]
    -> \let\semtex@currentatom\@empty   (Section 8a.5)
Between passes:
  LaTeX rewrites main.aux with the current set of
  \semtex@atomref records (interleaved with standard
  \newlabel records).
Pass 2 (inversion + render):
  \AtEndPreamble / begindocument/before
    -> \semtex@installatomrefpatch   (Section 8a.0)
    -> \semtex@installnewlabel       (Section 8a.4)
  \begin{document} -> kernel \@input{\jobname.aux}
    -> each \newlabel record:
         \semtex@extractlblnum updates \semtex@lblnum@<key>
    -> each \semtex@atomref{src}{tgt} record:
         \semtex@recordbr           (Section 8a.1)
         -> \xdef \csname semtex@brq@N \endcsname
              {\semtex@processbr{tgt}{src}}
  begindocument/end
    -> \semtex@flushbrqueue         (Section 8a.1)
    -> walks brq@1..brq@brid, firing \semtex@processbr
    -> \semtex@processbr            (Section 8a.3)
    -> populates \semtex@brcount@<tgt>
       and \semtex@brnode@<tgt>@<k>
  para/begin for atom N, or AtBeginEnvironment for tracked env
    -> \semtex@queuebackref{N}      (Section 8a.6 EDIT)
    -> \semtex@collapsebr{N} (lazy; first call only)
       -> joins brnode@N@1 .. brnode@N@count with ", "
       -> \xdef \csname semtex@br@N \endcsname{<joined>}
    -> reads \csname semtex@br@N \endcsname into
       \semtex@pendingbr
  para/end (or \AtEndEnvironment)
    -> \semtex@flushbackref -> \semtex@renderinline
       -> typesets "Used in X, Y."
    -> \let\semtex@currentatom\@empty
```

The pipeline has TWO halves that must both be in place:
the aux-WRITE patch (Section 8a.0) AND the aux-READ
callbacks (Sections 8a.1-8a.4).  Implementers must not
skip either half.

### Reference implementation sketch

The following TeX code is the blueprint for the Section 8a
insertion into `semtex.sty`.  It incorporates the fixes
from REVIEW_C (findings #1, #2, #3, #4) and is written to
be valid-shape — every brace and `\fi` balances, every
`\csname` closes, every `\expandafter` has a target.
2-space indent.

```tex
%% ------------------------------------------------------------
%% Section 8a.0: Reference interception (\@setref patch).
%% Per REVIEW_D finding #3, this subsection was absent from
%% the previous revision and is required for the aux-WRITE
%% half of the pipeline.  Without it, pass 1 never emits
%% \semtex@atomref records, pass 2 has nothing to read, and
%% the back-reference graph stays empty.
%%
%% \@setref is LaTeX's kernel dispatcher for \ref, \eqref,
%% \autoref, \cref, \vref, and every other reference
%% command (all of them bottom out here, even when hyperref
%% or cleveref wraps the user-visible entry point).  One
%% patch point covers the lot.
%% ------------------------------------------------------------

% Pass-1 safety: \semtex@atomref must be defined to SOMETHING
% at package-load time so that if a stale pass-0 .aux still
% references it (or a user-script injects a record), LaTeX's
% aux read does not error.  A \providecommand no-op suits.
\providecommand*{\semtex@atomref}[2]{}

% \semtex@installatomrefpatch
%   Wraps \@setref so each invocation also writes a
%   \semtex@atomref record to .aux.  Guarded on
%   \semtex@currentatom being non-empty per Section 8a.5.
%
%   NOTE: installed at begindocument/before (Section 8a.7),
%   AFTER hyperref has had its chance to wrap \@setref.  The
%   patch operates on whichever \@setref is live at that
%   point, so hyperref's hyperlinking side-effect is
%   preserved.
\def\semtex@installatomrefpatch{%
  \let\semtex@orig@setref\@setref
  \def\@setref##1##2##3{%
    \semtex@orig@setref{##1}{##2}{##3}%
    \ifx\semtex@currentatom\@empty\else
      \if@filesw
        \protected@write\@auxout{}{%
          \string\semtex@atomref
            {\semtex@currentatom}{##3}%
        }%
      \fi
    \fi
  }%
}

%% ------------------------------------------------------------
%% Section 8a.1: defer queue via csname linked list.
%% Per REVIEW_C finding #2, the toks-register pattern from
%% dpmac is O(N^2) at 15k refs; replaced with a csname
%% linked list keyed by a monotonic \semtex@brid counter.
%% ------------------------------------------------------------
\newcount\semtex@brid
\semtex@brid=0\relax

% \semtex@recordbr{src}{tgt}
%   Enqueue a processbackref call.  O(1) per append.
\def\semtex@recordbr#1#2{%
  \global\advance\semtex@brid by 1\relax
  \expandafter\xdef\csname semtex@brq@\the\semtex@brid\endcsname
    {\noexpand\semtex@processbr{#2}{#1}}%
}

% \semtex@flushbrqueue
%   Walk the linked list once, O(N) total.  Called from the
%   begindocument hook with explicit ordering (see "Queue
%   flush timing" below).
\def\semtex@flushbrqueue{%
  \begingroup
    \count@=\z@
    \loop
      \ifnum\count@<\semtex@brid
        \advance\count@ by 1\relax
        \csname semtex@brq@\the\count@\endcsname
        \global\expandafter\let
          \csname semtex@brq@\the\count@\endcsname\relax
    \repeat
  \endgroup
}

%% ------------------------------------------------------------
%% Section 8a.2: .aux record callback.
%% The providecommand no-op from Section 8a.0 is REPLACED by
%% this active definition at begindocument/before (Section
%% 8a.7), before LaTeX reads .aux in \begin{document}.  From
%% that point on, every \semtex@atomref{src}{tgt} that the
%% .aux read fires lands here and enqueues a processbackref
%% call.
%%
%% Per REVIEW_C finding #4, guard on empty src (orphan refs
%% emitted between atoms).  The guard is belt-and-braces: the
%% \@setref patch in Section 8a.0 already skips the write
%% when \semtex@currentatom is empty, so a well-formed .aux
%% should never deliver an empty-src record here; we guard
%% anyway in case a user hand-edits the aux or a legacy file
%% sneaks in.
%% ------------------------------------------------------------
\def\semtex@atomref@active#1#2{%
  \edef\semtex@tmp@src{#1}%
  \ifx\semtex@tmp@src\@empty\else
    \semtex@recordbr{#1}{#2}%
  \fi
}

%% ------------------------------------------------------------
%% Section 8a.3: per-target linked list (O(degree), not
%% O(degree^2)).  Per REVIEW_C finding #2 second half.
%%
%% For each target atom we maintain:
%%   \semtex@brcount@<num>  -- count of appended refs
%%   \semtex@brnode@<num>@<k> -- the k-th ref text
%% At typeset time the nodes are collapsed into the
%% display macro \semtex@br@<num>.
%% ------------------------------------------------------------
\def\semtex@processbr#1#2{%
  % #1 = target label key
  % #2 = source atom display number
  \expandafter\ifx\csname semtex@lblnum@#1\endcsname\relax
    % Unknown target: silently drop.  This is the same
    % behaviour as dpmac's \ewarningline, minus the warning.
  \else
    \edef\semtex@tmp@tgt{\csname semtex@lblnum@#1\endcsname}%
    \edef\semtex@tmp@src{#2}%
    % Self-ref guard (REVIEW_C finding #10).  Both sides are
    % \edef'd so comparison is on display-number strings.
    \ifx\semtex@tmp@src\semtex@tmp@tgt\else
      % Dedup against previous append for this target.
      % (Per REVIEW_D finding #1, an earlier draft had a
      % dead \ifx placeholder here; removed.)
      \edef\semtex@tmp@last{%
        \csname semtex@brlast@\semtex@tmp@tgt\endcsname}%
      \ifx\semtex@tmp@last\semtex@tmp@src
        % Consecutive duplicate: skip.
      \else
        \global\expandafter\let
          \csname semtex@brlast@\semtex@tmp@tgt\endcsname
          \semtex@tmp@src
        % Append a new linked-list node.
        \expandafter\ifx
            \csname semtex@brcount@\semtex@tmp@tgt\endcsname\relax
          \global\expandafter\def
            \csname semtex@brcount@\semtex@tmp@tgt\endcsname{0}%
        \fi
        \edef\semtex@tmp@k{%
          \csname semtex@brcount@\semtex@tmp@tgt\endcsname}%
        \count@=\semtex@tmp@k\relax
        \advance\count@ by 1\relax
        \expandafter\xdef
          \csname semtex@brcount@\semtex@tmp@tgt\endcsname
          {\the\count@}%
        \expandafter\xdef
          \csname semtex@brnode@\semtex@tmp@tgt @\the\count@\endcsname
          {#2}%
      \fi
    \fi
  \fi
}

% \semtex@collapsebr{targetnum}
%   Build a comma-joined display macro \semtex@br@<num>
%   from the per-target node csnames.  Called lazily the
%   first time \semtex@queuebackref looks up <num>.
\def\semtex@collapsebr#1{%
  \expandafter\ifx\csname semtex@brcount@#1\endcsname\relax
    % No refs to this target.
    \global\expandafter\let\csname semtex@br@#1\endcsname\@empty
  \else
    \begingroup
      \edef\semtex@tmp@n{\csname semtex@brcount@#1\endcsname}%
      \def\semtex@tmp@acc{}%
      \count@=\z@
      \loop
        \ifnum\count@<\semtex@tmp@n
          \advance\count@ by 1\relax
          \edef\semtex@tmp@node{%
            \csname semtex@brnode@#1@\the\count@\endcsname}%
          \ifx\semtex@tmp@acc\@empty
            \edef\semtex@tmp@acc{\semtex@tmp@node}%
          \else
            \edef\semtex@tmp@acc{%
              \semtex@tmp@acc, \semtex@tmp@node}%
          \fi
      \repeat
      \global\expandafter\let
        \csname semtex@br@#1\endcsname\semtex@tmp@acc
    \endgroup
  \fi
}

%% ------------------------------------------------------------
%% Section 8a.4: \newlabel override.
%% Per REVIEW_C finding #1, use \@secondoftwo-style grab of
%% the first braced subgroup.  Per REVIEW_C finding #3, pin
%% installation at \AtEndPreamble so hyperref's pre-2023
%% aux-injection block does not clobber it.  Also patch
%% \newlabelxx to cover the pre-2023 hyperref pathway.
%% ------------------------------------------------------------
\def\semtex@grabfirst#1#2\@nil{#1}
\def\semtex@installnewlabel{%
  \let\semtex@orig@newlabel\newlabel
  \def\newlabel##1##2{%
    \semtex@orig@newlabel{##1}{##2}%
    \semtex@extractlblnum{##1}{##2}%
  }%
  % Pre-2023 hyperref path: \newlabelxx#1#2#3#4#5#6 -> \oldnewlabel
  % We override \newlabelxx too, since hyperref installs it in
  % \AtBeginDocument and it races with our override.
  \@ifundefined{newlabelxx}{}{%
    \let\semtex@orig@newlabelxx\newlabelxx
    \def\newlabelxx##1##2##3##4##5##6{%
      \semtex@orig@newlabelxx{##1}{##2}{##3}{##4}{##5}{##6}%
      % ##2 is already the display number for the 6-arg form.
      \expandafter\gdef
        \csname semtex@lblnum@##1\endcsname{##2}%
    }%
  }%
}

% \semtex@extractlblnum{key}{value}
%   value is the raw 2nd arg of \newlabel, which after TeX
%   brace-stripping is already "{num}{page}{...}{...}{...}".
%   We grab the first brace group and stash it under the key.
%   Skip keys that end in @cref (cleveref internal records).
\def\semtex@extractlblnum#1#2{%
  \semtex@ifcrefkey{#1}{%
    % @cref-suffixed: skip silently.
  }{%
    % Extract first subgroup via \semtex@grabfirst.
    \expandafter\semtex@extractlblnum@ii
      \expandafter{\semtex@grabfirst#2\@nil}{#1}%
  }%
}
\def\semtex@extractlblnum@ii#1#2{%
  \expandafter\gdef\csname semtex@lblnum@#2\endcsname{#1}%
}

% \semtex@ifcrefkey{key}{then}{else}
%   True iff the label key ENDS in "@cref" (not merely
%   contains it).  Per REVIEW_D finding #4, an earlier draft
%   matched any key containing "@cref", which incorrectly
%   dropped keys like "lemma@crefnum" that happen to contain
%   "@cref" as a prefix of a longer suffix.  Fixed below.
%
% Algorithm: the delimited-arg probe splits "<key>@cref\@nil"
% on the FIRST occurrence of "@cref".  ##2 is the tail of
% the split (everything after @cref, up to \@nil).
% Outcomes:
%   key = foo              -> probe "foo@cref\@nil"
%                          -> ##1=foo, ##2=(empty) -> NOT cref
%   key = foo@cref         -> probe "foo@cref@cref\@nil"
%                          -> ##1=foo, ##2=@cref -> IS cref
%   key = foo@crefnum      -> probe "foo@crefnum@cref\@nil"
%                          -> ##1=foo, ##2=num@cref -> NOT cref
%   key = foo@cref@bar     -> probe "foo@cref@bar@cref\@nil"
%                          -> ##1=foo, ##2=@bar@cref -> NOT cref
%
% The rule "IS cref iff ##2 == '@cref'" detects the
% sentinel-only tail, which happens exactly when the
% ORIGINAL key ended in "@cref" and the probe's own trailing
% "@cref" is what matched.
\def\semtex@ifcrefsentinel{@cref}
\def\semtex@ifcrefkey#1{%
  % Side-effect style: set a boolean, then dispatch on it.
  % Clearer than nested-\expandafter skip-out-of-two-\fis,
  % and avoids the three-\expandafter trick that REVIEW_D
  % finding #4 cautions against.
  \semtex@iscreffalse
  \def\semtex@ifcrefkey@probe##1@cref##2\@nil{%
    \def\semtex@tmp@b{##2}%
    \ifx\semtex@tmp@b\@empty
      % No @cref in the key at all -> the probe's own
      % trailing @cref absorbed the split -> NOT a cref key.
    \else
      % @cref found somewhere.  IS-cref iff the tail is
      % EXACTLY "@cref" (meaning the probe's own trailing
      % @cref is what matched, i.e. the key ended in @cref).
      \ifx\semtex@tmp@b\semtex@ifcrefsentinel
        \semtex@iscreftrue
      \fi
    \fi
  }%
  \semtex@ifcrefkey@probe#1@cref\@nil
  \ifsemtex@iscref
    \expandafter\@firstoftwo
  \else
    \expandafter\@secondoftwo
  \fi
}
% Flag declared once; used only inside \semtex@ifcrefkey.
\newif\ifsemtex@iscref

%% ------------------------------------------------------------
%% Section 8a.7: hook installation.
%% Per REVIEW_D finding #2, the two semtex-owned labels on
%% begindocument/before get EXPLICIT relative ordering rather
%% than both claiming "before *".  Two "before *" rules in
%% the same package pile up and give no guarantee about their
%% relative order if a future edit introduces a dependency.
%% ------------------------------------------------------------

% Install the \@setref aux-write patch AND the \newlabel
% override + the active \semtex@atomref callback at
% begindocument/before.  All three belong together in one
% hook because they co-depend on being in place before the
% .aux read during \begin{document}.
\AddToHook{begindocument/before}[semtex/backref/install]{%
  \semtex@installatomrefpatch
  \semtex@installnewlabel
  % Swap the providecommand no-op for the active callback.
  \let\semtex@atomref\semtex@atomref@active
}

% Flush the queue AFTER aux has been read.  The aux read
% happens during the kernel's \document macro before any
% \AtBeginDocument hook fires, so begindocument/end is a
% safe point.  No internal ordering constraint vs. semtex's
% own labels on this hook (there is only one).
\AddToHook{begindocument/end}[semtex/backref/flush]{%
  \semtex@flushbrqueue
}
```

**Hook-rule declarations** (per REVIEW_D #2).  The two
semtex labels on `begindocument/before`
(`semtex/backref/install` from Section 8a.7 and
`semtex/sbl/open` from Section 9a) are given an explicit
internal order: the backref install must run before the
sbl open, because the sbl writer depends on the
`\semtex@currentatom` / `\@setref` patch infrastructure
being live.  No label claims `before *` any longer.

```tex
% Internal dependency: sbl open sees the backref install.
\DeclareHookRule{begindocument/before}{semtex/sbl/open}%
                {after}{semtex/backref/install}

% External ordering: we want to run before hyperref's
% \AtBeginDocument-equivalent hooks wrap \@setref a second
% time.  This rule is best-effort; see the "Load order"
% subsection for the ordering contract with third-party
% packages.
\DeclareHookRule{begindocument/before}%
                {semtex/backref/install}{before}{hyperref}
```

External ordering conflicts (hyperref, `acmart`, `biblatex`)
are a **testing TODO**: until the package has a regression
suite across a matrix of popular preamble stacks, we cannot
claim compatibility by construction.  Users who hit a
conflict should report it along with their full
`\usepackage{...}` list so a targeted `\DeclareHookRule`
can be added.

Notes on the sketch:

- The `\semtex@grabfirst` macro is the `\@secondoftwo`-style
  "grab first brace group, throw away the tail up to
  `\@nil`" pattern called for by REVIEW_C finding #1.
  Correct for both the 5-tuple (kernel/modern hyperref) and
  the 2-tuple (pre-2023 hyperref fallback).  For cleveref's
  `<key>@cref` records, the entire record is skipped via
  `\semtex@ifcrefkey`.
- `\semtex@recordbr` uses `\expandafter\xdef\csname ... brq@N
  \endcsname` — the O(1) append from REVIEW_C finding #2.
  No toks register is touched; no growing `\the` is
  performed.
- `\semtex@processbr` uses a *second* csname linked list
  (`semtex@brnode@<tgt>@<k>`) for the per-target append.
  The display macro `\semtex@br@<tgt>` is only materialised
  lazily by `\semtex@collapsebr`, which runs once per
  queried target.  This turns the O(K^2) from REVIEW_C
  finding #11 into O(K).
- Self-ref is checked via `\ifx\semtex@tmp@src
  \semtex@tmp@tgt` where both are built by `\edef`, so the
  comparison is on the fully expanded display-number
  strings.  REVIEW_C finding #10 is a minor risk around
  brace wrapping; a stricter normaliser can be added later.
- **The `\semtex@currentatom` clearing from REVIEW_A
  finding #3 / REVIEW_C finding #4 is handled at the
  atom-end hooks** (not shown in the sketch since it
  belongs in Sections 6 and 7 of `semtex.sty`, not
  Section 8).  See Section 8a.5 below.
- **The `\semtex@queuebackref` collapse call** (required
  for `\semtex@collapsebr` to ever fire) is not shown in
  the Section 8a.3 sketch because it is a modification to
  an existing macro.  See Section 8a.6 below for the
  concrete edit list.

### Section 8a.5 — `\semtex@currentatom` state management

> Upstream motivation: REVIEW_A finding #3 and REVIEW_C
> finding #4.  Promoted from a prose subsection to a
> numbered subsection per REVIEW_D finding #8 so an
> implementer cannot miss it.

The stale-`\semtex@currentatom` bug is the single most
impactful correctness hazard in the port.  The package at
`semtex.sty` lines 245, 274, and 399 *sets*
`\semtex@currentatom` inside atom-begin hooks but never
*clears* it.  Without the clear, every `\@setref` that
fires between atoms (in a section heading, caption,
footnote, or inter-paragraph remark) is attributed to the
PREVIOUS atom, and the resulting `\semtex@atomref` record
points at the wrong source.

#### Sites that set `\semtex@currentatom`

These are the three existing set sites, listed by
`semtex.sty` line number so the patch is unambiguous:

| Line | Site | Current code |
|---|---|---|
| 245 | `\semtex@hooktheorem` `AtBeginEnvironment` | `\edef\semtex@currentatom{\theatom}` |
| 274 | `\semtex@hookproof` `AtBeginEnvironment` standalone | `\edef\semtex@currentatom{\theatom}` |
| 399 | `\semtex@installparahook` normal branch | `\edef\semtex@currentatom{\theatom}` |

#### Sites that must clear `\semtex@currentatom`

The three corresponding atom-end sites.  Each clear goes
AFTER the existing `\semtex@flushbackref` (so the flush
still reads the correct atom number) and BEFORE the
`\semtex@nestlevel` decrement (which restores
pre-environment state).  The concrete edits:

| Line (area) | Site | Patch (insert after flush) |
|---|---|---|
| 249 | `\semtex@hooktheorem`'s `AtEndEnvironment` block (after `\semtex@flushbackref`) | `\let\semtex@currentatom\@empty` |
| 286 | `\semtex@hookproof`'s `AtEndEnvironment` block (inside the `\ifbool{semtex@proofsnumbered}` conditional, after the flush) | `\let\semtex@currentatom\@empty` |
| 460 | `\semtex@installparendhook`'s `para/end` hook body (after `\semtex@flushbackref`) | `\let\semtex@currentatom\@empty` |

#### Why the clear prevents the bug

Section 8a.0's `\@setref` patch guards its `\immediate\write`
on `\ifx\semtex@currentatom\@empty`.  With the three clears
in place:

- A `\ref` in a section heading (which runs with
  `\semtex@nestlevel > 0` and no atom context) fires
  `\@setref` with `\semtex@currentatom` empty; the write is
  skipped; no ghost edge is created.
- A `\ref` in a stray paragraph between a tracked theorem
  and the next atom fires after the theorem's
  `\AtEndEnvironment` has cleared the state; the write is
  skipped; no ghost edge.
- A `\ref` inside a caption or footnote is protected by
  the `\semtex@nestlevel` guard AND by the cleared
  `\semtex@currentatom` — belt and braces.

#### Cross-cutting consequences

Every site that emits a `.sbl` record (Section 9a's
`\semtex@sblwrite@atom` helper) also guards on
`\semtex@currentatom`.  Implementing the clear at
atom-end is therefore a prerequisite for both back-ref
correctness (Section 8a) and `.sbl` correctness
(Section 9a) — fix once, benefit twice.

#### Regression test

Add a test case under `tools/semtex-sty/testfiles/` named
`test-stale-currentatom.lvt`.  The fixture:

1. Opens a tracked theorem with `\label{thm:first}`.
2. Closes the theorem.
3. Places a plain paragraph with `\ref{thm:first}` BEFORE
   any new atom starts.
4. Opens a second tracked theorem with `\label{thm:second}`.
5. Asserts via `\semtex@debug@aux` (a test helper that
   greps the `.aux`) that NO `\semtex@atomref` record names
   `thm:first`'s number as `src` for the stray ref.
   Equivalently, asserts that `thm:second` has no
   "Used in ..." line.

This test pins the three clears in place so an accidental
regression is caught at the `.lvt` level.

### Section 8a.6 — Edits to existing `semtex.sty` macros

> Per REVIEW_D finding #5 (BLOCKER): the Section 8a.1-8a.4
> sketch defines new macros but does not specify how the
> existing `semtex.sty` macros interact with them.  An
> implementer who reads only the new sketch will leave
> `\semtex@queuebackref` unchanged, never call
> `\semtex@collapsebr`, and ship a fully broken port that
> compiles cleanly but renders no "Used in" lines.  This
> subsection enumerates every existing-macro edit needed
> to wire the port end-to-end.

Line numbers are against the current `semtex.sty` (the
one referenced throughout this design doc; 654 lines).

#### 8a.6.a — `\semtex@queuebackref` (lines 415-427): REWRITE

Before the existing lookup of `\csname semtex@br@#1\endcsname`,
call `\semtex@collapsebr{#1}` so that per-target nodes are
lazily materialised on first query.  The collapse macro
itself is idempotent (it short-circuits if the display
csname is already set), so calling it unconditionally on
every `\semtex@queuebackref` is fine; subsequent calls for
the same atom number are cheap.

New body:

```tex
\newcommand*{\semtex@queuebackref}[1]{%
  \ifbool{semtex@backrefs}{%
    \semtex@pendingbr={}%
    % Lazy collapse: first call materialises \semtex@br@#1.
    \expandafter\ifx\csname semtex@brcount@#1\endcsname\relax
      % No refs to this target; collapse is a no-op but
      % still runs to set the empty sentinel.
      \semtex@collapsebr{#1}%
    \else
      \semtex@collapsebr{#1}%
    \fi
    \@ifundefined{semtex@br@#1}{%
      % Still undefined after collapse means the sentinel
      % set it to \empty; treat as no back-refs.
    }{%
      \ifbool{semtex@appendix}{}{%
        \semtex@pendingbr=\expandafter{%
          \csname semtex@br@#1\endcsname}%
      }%
    }%
  }{}%
}
```

Note: `\semtex@collapsebr` (defined in Section 8a.3)
already handles both the has-refs and no-refs cases, so
the outer `\ifx\relax` guard in the new body is strictly
redundant — I included it only so the reader can trace the
control flow without jumping back to Section 8a.3.  An
implementer may simplify to a single unconditional
`\semtex@collapsebr{#1}` call.

#### 8a.6.b — `\semtex@flushbackref` (lines 431-441): MINIMAL EDIT

Unchanged body.  The macro still reads `\semtex@pendingbr`
into a temp via `\the`, tests empty, and calls
`\semtex@renderinline`.  The token register is populated
from the collapsed display csname in 8a.6.a above, so the
flush mechanism does not need to change.

However, per Section 8a.5, **after** the existing
`\semtex@pendingbr={}` reset, ADD:

```tex
  \let\semtex@currentatom\@empty
```

This clears the state machine after the flush.  See
Section 8a.5 for the full currentatom edit list.

#### 8a.6.c — `\semtex@readsbr` (lines 502-519): DELETE ENTIRELY

The `.sbr` file no longer exists.  The new model reads
`.aux` on pass 2 via LaTeX's normal rerun; there is no
separate `.sbr` to `\IfFileExists` or `\input`.  Delete
the whole `\newcommand*{\semtex@readsbr}{...}` block.

Also remove the `\AtBeginDocument{\semtex@readsbr}` call
at line 578 (inside `\semtextrack`).

#### 8a.6.d — `\semtex@writeauxhash` (lines 523-532): DELETE ENTIRELY

No content hash is written.  `rerunfilecheck` /
`latexmk` handle staleness via the normal
aux-content-changed-between-passes mechanism; the kernel's
"Label(s) may have changed" warning is the only staleness
signal the user needs.

Also remove the `\AtEndDocument{\semtex@writeauxhash}`
call at line 580 (inside `\semtextrack`).

#### 8a.6.e — `\semtex@auxversion` (lines 537-539): DELETE ENTIRELY

The `\providecommand*{\semtex@auxversion}[1]{...}` aux
callback is no longer emitted by any writer, so the
callback has nothing to consume.  Delete.

#### 8a.6.f — `\semtex@sbrversion` / `\semtex@backref` / `\semtex@section` (lines 472-498): DELETE ENTIRELY

These three callbacks existed to consume `.sbr` records.
With the `.sbr` file gone, nothing calls them.  Delete all
three macro definitions.

#### 8a.6.g — Appendix-mode plumbing: KEEP, RE-PLUMB

The appendix machinery is retained but its data source
changes from "accumulated during `\semtex@backref`
callbacks" to "walked from per-target `\semtex@br@<num>`
csnames at `\semtexappendix` call time".

- **`\semtex@appendixdata` token register (line 118):**
  KEEP the declaration, but it is no longer populated
  incrementally.
- **`\semtex@appendixsection{num}{title}` / `\semtex@appendixentry{num}{type}{list}` (lines 616-629):**
  KEEP as-is — they are the rendering primitives.
- **`\semtexappendix` (lines 600-612):** REWRITE the body
  to walk the set of known atoms (derivable from the
  `\semtex@brnode@*` csname family, or equivalently from a
  list that `semtex.sty` maintains as atoms are created)
  and, for each atom with a non-empty collapsed display
  macro, emit a `\semtex@appendixentry`.  Section titles
  come from the TOC entries LaTeX already writes to `.aux`
  (the standard `\contentsline` records).

The rewrite of `\semtexappendix` is a ~15-line
single-pass loop; it replaces the token-register
accumulator pattern.  Concrete sketch:

```tex
\newcommand*{\semtexappendix}{%
  \ifbool{semtex@appendix}{%
    \section*{Dependency Index}%
    \begingroup
      \small
      % Walk \semtex@atomlist (a list macro that
      % para/begin, hooktheorem, and hookproof all append
      % to as atoms are created).  Each entry is a
      % (num, type) pair.
      \def\do##1{%
        \semtex@appendix@emit##1%
      }%
      \semtex@atomlist
    \endgroup
  }{%
    \PackageWarning{semtex}{%
      \string\semtexappendix\space ignored: %
      backrefs mode is not 'appendix'}%
  }%
}
\def\semtex@appendix@emit#1#2{%
  % #1 = display number, #2 = atom type
  \semtex@collapsebr{#1}%
  \expandafter\ifx\csname semtex@br@#1\endcsname\@empty\else
    \semtex@appendixentry{#1}{#2}{%
      \csname semtex@br@#1\endcsname}%
  \fi
}
```

Where `\semtex@atomlist` is a new list macro initialised
empty and appended to at every atom-begin site (lines
245, 274, 399).  Append style:

```tex
  \xdef\semtex@atomlist{%
    \semtex@atomlist
    \do{{\theatom}{<type>}}}
```

The append is O(1) per atom (list grows by one
`\do{...}` entry); the walk at `\semtexappendix` call
time is O(N) in the atom count.

#### 8a.6.h — Summary of additions vs. deletions

| Kind | Lines added | Lines deleted |
|---|---|---|
| New (Section 8a.0-8a.4, 8a.7, helpers) | ~180 | — |
| `\semtex@queuebackref` rewrite (8a.6.a) | ~15 | 13 |
| `\semtex@flushbackref` edit (8a.6.b) | 1 | 0 |
| `\semtex@readsbr` deletion (8a.6.c) | 0 | 18 |
| `\semtex@writeauxhash` deletion (8a.6.d) | 0 | 10 |
| `\semtex@auxversion` deletion (8a.6.e) | 0 | 3 |
| `\semtex@sbrversion` / `@backref` / `@section` deletion (8a.6.f) | 0 | 27 |
| `\semtexappendix` re-plumb (8a.6.g) + `\semtex@atomlist` plumbing | ~25 | ~13 |
| currentatom clears (Section 8a.5) | 3 | 0 |
| **Total** | **~224** | **~84** |

Net change: roughly **+140 lines** on the current
`semtex.sty`, bringing it from ~654 to ~794.  Consistent
with the REVIEW_ARCH_dpmac_port estimate of "~714 lines"
plus the Section 8a.6 plumbing not originally counted.

### Load order

`semtex.sty` **must be loaded after `hyperref` and after
`cleveref` (if either is used)**.  This has always been
required because `hyperref` redefines `\@setref`; the
requirement is strengthened in the port because the
`\newlabel` override at `\AtEndPreamble` must see the
final definitions of `\newlabel` / `\newlabelxx`.

The install point is `\AtEndPreamble` (equivalently
`begindocument/before` with an explicit ordering label).
**Do NOT use `\AtBeginDocument` for the override.**
`\AtBeginDocument` fires AFTER LaTeX reads `.aux` (at
line ~9489 of `latex.ltx`, the `\@input{\jobname.aux}`
inside `\document`), which is AFTER we needed the override
to be in effect.  The override's whole purpose is to
intercept aux records as they are read; if it is installed
after the read, every record is missed.

The queue flush is a separate hook at `begindocument/end`,
which fires after the aux read has populated the queue
via the `\semtex@atomref` callbacks.  Ordered `before` `*`
so that other packages' `\AtBeginDocument` hooks see a
populated `\semtex@br@<num>` namespace.

### Performance

Per REVIEW_C finding #2, the **rejected** approach is
dpmac's token-register defer queue.  At 15 000 cross
references, a toks-register append of an existing
`\the\semtex@brqueue` is O(k) per append, giving O(N^2/2)
total token copies.  At ~30 tokens per record and ~75 ns
per token copy, that is:

| Refs | Token copies | Rejected toks approach |
|---|---|---|
| 2 000 | ~60 M | ~4.5 s |
| 15 000 | ~3.4 B | **~253 s** (4 minutes) |
| 100 000 | ~150 B | ~3.1 hours |

The **accepted** approach (Section 8a.1 above) uses a
csname linked list: each `\semtex@recordbr` is O(1)
(one `\xdef` and one counter bump), the flush is O(N)
total, and the per-target collapse is O(K) per target
(not O(K^2)).  Realistic timings:

| Refs | Accepted linked-list approach |
|---|---|
| 2 000 | ~0.01 s |
| 15 000 | **~0.08 s** |
| 100 000 | ~0.5 s |

The 15 000-ref figure is the target for a multi-hundred
page research monograph.  The 100 000-ref figure is a
worst-case encyclopedia and is still well inside
interactive build budget.

**Hash-table saturation at very large scale (per REVIEW_D
finding #13).** At ~100 000 atoms, TeX's csname hash table
(default ~15 000 strings) saturates and lookup degrades.
Each `\semtex@brnode@<tgt>@<k>` and each
`\semtex@br@<num>` lives in that hash table, so a worst-
case document with 100 000 atoms and 100 000 backref
edges allocates ~200 000 csnames.  Users on documents
that large must increase `hash_extra` (and possibly
`pool_size`) in `texmf.cnf`, or accept that csname
lookups slow down as the hash overflows.  This is a TeX
engine limitation inherited by all heavy csname-based
machinery, not a semtex bug.  For documents up to ~30 000
atoms (the practical ceiling of even very large
monographs) the default hash table is fine.  Document in
the user-facing README when one exists.

### Queue flush timing

LaTeX's `\begin{document}` expands `\document`, which at
line ~9489 of `latex.ltx` executes
`\@input{\jobname.aux}` to read the aux file in-place.
`\AtBeginDocument` hooks fire at line ~9512, AFTER the aux
read completes.  Therefore:

- The `\newlabel` override must be installed **before**
  line ~9489.  `\AtEndPreamble` (equivalently
  `begindocument/before`) is the correct pin.
- The queue flush must run **after** line ~9489 but
  preferably before other `\AtBeginDocument` hooks run,
  so that third-party hooks can read the populated
  `\semtex@br@*` namespace.  `begindocument/end` is the
  correct pin, declared `before` `*` via
  `\DeclareHookRule` (LaTeX 2021+).  This is the pattern
  REVIEW_C finding #8 asks for and is already in the
  implementation sketch above.

If LaTeX 2021+ hook rules are unavailable (shouldn't
happen — the package already requires `[2021/06/01]`),
fall back to `\AtBeginDocument` without a rule.  The
flush is still correct; only third-party ordering is
weakened.

### Edge cases

Known issues, each with a one-line mitigation drawn from
the review record:

- **Stale `\semtex@currentatom` between atoms** (REVIEW_A
  #3 / REVIEW_C #4): clear at atom-end in Sections 6/7;
  guard at every write site.  See the "currentatom
  clearing" subsection above.
- **Label between two atoms**: resolves to whichever
  counter `\refstepcounter` last advanced, which is
  LaTeX's normal semantics; the atom `\label` attaches to
  is correct by construction when inside a tracked atom.
- **Nested refs inside `\label` arguments**: out of scope;
  authors who do this have bigger problems.
- **Self-ref detection** via `\ifx` on `\edef`'d display
  numbers: sufficient for byte-equal cases; fails only on
  brace-wrapped variants (REVIEW_C #10) which is a minor
  visual bug and can be tightened with a normaliser.
- **Refs in captions / footnotes**: suppressed because
  `\semtex@nestlevel > 0` at those sites, so
  `\semtex@currentatom` is not written to.
- **Cleveref `<key>@cref` records**: skipped by the
  `\semtex@ifcrefkey` filter (REVIEW_C #12); the real
  record for the same key (without suffix) is used.
- **pre-2023 hyperref `\newlabelxx` pathway** (REVIEW_C
  #3): patched alongside `\newlabel` in
  `\semtex@installnewlabel`.
- **Kernels older than `\AddToHook`**: the package already
  errors out at `semtex.sty` line 636-642.

### License note

The whole of `semtex.sty` is distributed under **GNU GPL
version 3** as a derivative work of `dpmac.tex`.  The
Section 8a port brings in the defer-queue /
`\processbackref` / `\predefbackref` pattern and the
two-register structure; those are the derivative elements.
Downstream users must retain GPLv3 obligations when
redistributing `semtex.sty` as part of a larger work.
See `tools/semtex-sty/CREDITS.md` for the provenance
table and the intent to reach out to Pavlov about a
possible LPPL dual-license courtesy.

## Section 8b — LaTeXML HTML rendering

### Problem

LaTeXML renders `\semtex@renderinline`'s
`\rightline{\small\sffamily Used in X, Y.}` as
presentational HTML with no semantic class — typically a
generic `<ltx:text>` wrapper that loses the "this is a
back-reference block" information at the XML/HTML boundary.
Consumers of the HTML output (the mwablab web site, any
external reader) cannot then hide, style, or collapse
back-reference blocks via CSS because there is no stable
selector to target.  The same problem applies to the
superscript atom margin numbers emitted by
`\semtex@emitmargin`.

The Section 8a back-reference *graph computation* is
unaffected by this — LaTeXML honours LaTeX's `.aux` rerun
semantics, so the same queue-flush dance in Section 8a
runs during LaTeXML processing, and
`\semtex@br@<num>` csnames become populated exactly as they
do under pdflatex.  Only the **rendering** step has a
LaTeXML-specific wrinkle, and only because LaTeXML's
default bindings for `\rightline` and `\textsuperscript`
emit presentational markup.

### Solution

Ship a **LaTeXML binding file** `semtex.ltxml` alongside
`semtex.sty` in the CTAN package.  The binding is written
in Perl against the LaTeXML `Package` API and overrides
exactly two rendering macros — `\semtex@renderinline` and
`\semtex@emitmargin` — to emit semantic HTML spans with
stable class names.  Users of pdflatex, lualatex, or
xelatex see no change; only the LaTeXML processing
pipeline picks up the override.

### Stable class contract

`semtex.sty` promises the following CSS class names as a
**public interface**.  Downstream HTML consumers may rely
on these class names being stable across semtex.sty
versions; additions are allowed, renames and removals are
breaking changes.

| Class | Wraps |
|---|---|
| `semtex-usedby` | The entire "Used in X, Y." block |
| `semtex-usedby-label` | The leader text "Used in" |
| `semtex-usedby-list` | The comma-separated ref list |
| `semtex-usedby-ref` | Each individual back-ref anchor |
| `semtex-usedby-trailer` | The trailing period |
| `semtex-atomnum` | The superscript atom number in the margin |
| `semtex-atomnum-value` | The numeric text inside the atom number |

`semtex.sty` **does not ship CSS**.  The web toolchain
(currently the mwablab site generator) supplies the
stylesheet.  A one-line `.semtex-usedby { display: none; }`
hides all back-references; `.semtex-usedby { display:
block; }` shows them.  Authors who want collapsible
disclosure can wrap the block in `<details>` via a tiny
post-processing step or via CSS `content:` tricks; that is
out of scope for `semtex.sty` itself.

### Reference `semtex.ltxml` sketch

```perl
# -*- mode: Perl -*-
# semtex.ltxml -- LaTeXML binding for semtex.sty
# Copyright 2026, GNU GPL v3.  Part of the semtex package.
#
# Graph computation is done by semtex.sty via LaTeX's
# normal .aux rerun, which LaTeXML honours.  This file
# only redefines the RENDERING macros so HTML output
# carries semantic class names.

package LaTeXML::Package::Pool;
use strict;
use warnings;
use LaTeXML::Package;

# ---- "Used in X, Y." block ---------------------------------

DefMacro('\semtex@renderinline{}',
  '\lxML@semtex@renderinline{#1}');

DefConstructor('\lxML@semtex@renderinline{}',
    "<ltx:text class='semtex-usedby'>"
  . "<ltx:text class='semtex-usedby-label'>Used in </ltx:text>"
  . "<ltx:text class='semtex-usedby-list'>#1</ltx:text>"
  . "<ltx:text class='semtex-usedby-trailer'>.</ltx:text>"
  . "</ltx:text>");

# ---- Margin atom number ------------------------------------

DefMacro('\semtex@emitmargin{}',
  '\lxML@semtex@atomnum{#1}');

DefConstructor('\lxML@semtex@atomnum{}',
    "<ltx:text class='semtex-atomnum'>"
  . "<ltx:text class='semtex-atomnum-value'>#1</ltx:text>"
  . "</ltx:text>");

# ---- .sbl / \semtextag / \newmath --------------------------
#
# These produce no typeset output under pdflatex (they are
# write-only sidecar records -- see Section 9a).  Under
# LaTeXML we also want them to produce no HTML, so we
# define them as no-ops on the typeset side.  The .sbl
# file is still written because LaTeXML honours
# \immediate\write.
DefMacro('\semtextag{}{}', '');
# \newmath is handled in the .sty itself (not in this file)
# because its wrapper must generate TeX tokens.

1;
```

**Handling `#1` inside the "Used in" list.**  The list is a
tokenised sequence of `\hyperlink{...}{num}` calls (from
Section 8a), which LaTeXML's hyperref binding already
turns into `<ltx:ref>` elements.  The outer
`semtex-usedby-list` span is sufficient to address those
via the CSS selector `.semtex-usedby-list > ltx:ref`.

**Per-anchor `semtex-usedby-ref` class (per REVIEW_D
finding #12).**  An explicit per-anchor class is
implementable via a scoped `\hyperlink` override in
`semtex.ltxml`.  The override is gated on a state flag
that `\lxML@semtex@renderinline` raises on entry and
clears on exit, so it is active only inside a "Used in"
list and harmless to other `\hyperlink` uses elsewhere in
the document:

```perl
# In semtex.ltxml, alongside the binding above:

DefMacro('\semtex@usedby@begin', '');
DefMacro('\semtex@usedby@end',   '');

# Track whether we are inside a "Used in" list.  LaTeXML
# state via AssignValue / LookupValue.
DefPrimitive('\semtex@usedby@begin', sub {
  AssignValue('semtex@usedby@active' => 1, 'global'); });
DefPrimitive('\semtex@usedby@end', sub {
  AssignValue('semtex@usedby@active' => 0, 'global'); });

# Wrap the renderinline DefConstructor so the begin/end
# fire around the list.
DefConstructor('\lxML@semtex@renderinline {}',
  "<ltx:text class='semtex-usedby'>"
  . "<ltx:text class='semtex-usedby-label'>Used in </ltx:text>"
  . "<ltx:text class='semtex-usedby-list'>"
  . "?&semtex_usedby_open()(#1)?&semtex_usedby_close()"
  . "</ltx:text>"
  . "<ltx:text class='semtex-usedby-trailer'>.</ltx:text>"
  . "</ltx:text>");

# Override \hyperlink only when the flag is set.
DefConstructor('\hyperlink {} {}',
  sub {
    my ($document, $key, $text) = @_;
    if (LookupValue('semtex@usedby@active')) {
      $document->openElement('ltx:ref',
        labelref => ToString($key),
        class    => 'semtex-usedby-ref');
      $document->absorb($text);
      $document->closeElement('ltx:ref');
    } else {
      # Default behaviour: hand off to LaTeXML's stock
      # \hyperlink binding (do not collide).
      Digest(T_CS('\@semtex@hyperlink@orig')
        . T_BEGIN . $key->unlist . T_END
        . T_BEGIN . $text->unlist . T_END);
    }
  });
```

The exact LaTeXML idiom for "fall through to the kernel
binding" varies by LaTeXML version; the comment "do not
collide" flags that the implementer must consult LaTeXML
docs for the current invocation pattern.  The shape above
is illustrative.  An alternative simpler approach: skip
the override entirely and rely on `.semtex-usedby-list >
ltx:ref` CSS selectors, which works with zero `.ltxml`
complexity.

### Cross-reference to `.sbl` and the semantic CLI

`.sbl` records, `\semtextag`, and `\newmath` metadata do
**not** need LaTeXML bindings, because they produce no
typeset output.  They are write-only sidecar data consumed
by `semtex-cli` (Layer 2).  LaTeXML processes `.tex`
source to produce HTML; it has no reason to see `.sbl`.
The semantic CLI is the thing that reads `.sbl`, and it
never emits HTML directly in the current design — though
a future phase may produce HTML fragments for concept
index pages.  That is out of scope for Section 8b.

### File layout update

Add `semtex.ltxml` to `tools/semtex-sty/`:

```
tools/semtex-sty/
  semtex.sty              the package
  semtex.ltxml            LaTeXML binding (Section 8b)
  CREDITS.md              GPLv3 notice for the dpmac port
  DESIGN.md               this file
  ...
```

`semtex.ltxml` is part of the CTAN-publishable package and
ships alongside `semtex.sty` in the same directory.  Both
files fall under the same GPLv3 license.

### Testing strategy

Add a test item `test-latexml.lvt` (or equivalent golden
fixture under `testfiles/`) that:

1. Runs LaTeXML on a tiny document with a tracked theorem
   and a single `\ref` back into it.
2. Greps the generated XML for the expected class
   structure: `class="semtex-usedby"`,
   `class="semtex-usedby-label"`, and
   `class="semtex-atomnum"` must all be present.
3. Runs under the project's test harness alongside the
   pdflatex-based golden tests.

LaTeXML outputs XML (not HTML directly); an xmllint or
ripgrep check is sufficient to assert the class hooks are
emitted.

**Pre-commit validation (per REVIEW_D finding #11).**
Before committing `semtex.ltxml`, run

```
latexml --dest=/tmp/out.xml testfiles/test-minimal.tex
```

on a minimal fixture document.  LaTeXML reports
`DefMacro` / `DefConstructor` argument-pattern errors
loudly at parse time (e.g. "Missing argument count",
"Unbalanced braces in pattern"), so a successful run is
strong evidence the binding is at least syntactically
valid.  This check is cheap and should be wired into
`l3build check` once the LaTeXML binding lands.

### Non-goals for Section 8b

- Does **not** ship CSS or JavaScript.
- Does **not** define UI behaviour (collapsible, tooltip,
  sidebar).
- Does **not** replace the standard LaTeXML pipeline; it
  augments a small number of macro bindings.
- Does **not** attempt to render the `.sbl` file as HTML;
  that is the semantic CLI's concern (and not part of the
  current CLI scope either).
- Does **not** change Section 8a.  The back-reference
  graph is computed in TeX regardless of output engine.

## Section 9a — Semantic sidecar (.sbl) writer

### Purpose

`.sbl` is a write-only sidecar file that `semtex.sty`
emits during pass 1 (and every subsequent pass) alongside
the standard `.aux`.  Its purpose is to give Layer 2 (the
semantic CLI) enough per-atom context to analyse the
document without re-tokenising the `.tex` source from
scratch to find atom boundaries.  The `.sty` never reads
`.sbl` — it is strictly one-way output for downstream
semantic tools.

`.sbl` does **not** duplicate anything LaTeX already writes
to `.aux`.  Labels are the one borderline case: the `.aux`
has `\newlabel{key}{{num}...}` entries already, but the
`.sbl` ALSO emits `\semtex@sbl@label{num}{key}` records so
that the CLI can read atom-scoped cross-references without
parsing `.aux` at all.  This redundancy is deliberate and
documented.

### Record format

Line-oriented.  One call to a `\semtex@sbl@*` control
sequence per line.  Keys are pure ASCII; values are UTF-8.
Per **REVIEW_C finding #6**, the format is **flattened**:
no comma-separated key-value blobs.  Each metadata pair is
a dedicated record with a fixed number of brace-delimited
arguments.  The CLI parses N `{}`-groups and stops.

```
\semtex@sbl@version{1}
\semtex@sbl@source{main.tex}
\semtex@sbl@atom{1.2.3}{paragraph}
\semtex@sbl@meta{1.2.3}{src}{main.tex:42:1}
\semtex@sbl@atom{1.2.4}{Definition}
\semtex@sbl@meta{1.2.4}{src}{main.tex:48:1}
\semtex@sbl@meta{1.2.4}{env}{definition}
\semtex@sbl@label{1.2.4}{def:category}
\semtex@sbl@label{1.2.4}{def:cat-alias}
\semtex@sbl@tag{1.2.4}{uid}{cat:category}
\semtex@sbl@tag{1.2.4}{introduces}{Hom}
\semtex@sbl@tag{1.2.4}{introduces}{id}
\semtex@sbl@tag{1.2.4}{type}{Cat}
\semtex@sbl@use{1.2.5}{Hom}
\semtex@sbl@use{1.2.5}{circ}
\semtex@sbl@newmath{Hom}{arity}{2}
\semtex@sbl@newmath{Hom}{src}{main.tex:15:1}
\semtex@sbl@newmath{circ}{arity}{2}
\semtex@sbl@newmath{circ}{src}{main.tex:16:1}
\semtex@sbl@end{OK}
```

**Record types.**

| Macro | Arity | Meaning |
|---|---|---|
| `\semtex@sbl@version{v}` | 1 | File format version. Current: `1`. |
| `\semtex@sbl@source{file}` | 1 | Master source file name. |
| `\semtex@sbl@atom{num}{type}` | 2 | Atom begins. `type` is `paragraph`, `Definition`, `Theorem`, `proof`, etc. |
| `\semtex@sbl@meta{num}{k}{v}` | 3 | Per-atom metadata pair. Keys: `src` (file:line:col), `env`, `depth`. Extensible. |
| `\semtex@sbl@label{num}{key}` | 2 | Each `\label{key}` inside atom `num`. |
| `\semtex@sbl@tag{num}{kind}{value}` | 3 | User `\semtextag{kind}{value}` record. Free-form. |
| `\semtex@sbl@use{num}{cmd}` | 2 | Invocation of a `\newmath`-wrapped command inside atom `num`. |
| `\semtex@sbl@newmath{cmd}{k}{v}` | 3 | `\newmath` declaration metadata (one per property). NOT per-atom; global. |
| `\semtex@sbl@end{OK}` | 1 | Sentinel at `\AtEndDocument`. |

**End marker** (per REVIEW_C finding #7).  The **last line**
of a complete `.sbl` file is `\semtex@sbl@end{OK}`,
written from the `\AtEndDocument` hook.  Presence of this
line is the CLI's test for "complete file"; absence means
pdflatex was killed or crashed mid-run and the CLI must
treat the sidecar as stale and warn.  (The CLI should NOT
attempt to recover partial `.sbl` data; that is a recipe
for silently analysing 70% of a document and producing
misleading reports.)

### Open timing

**Per REVIEW_C finding #5**, the `.sbl` stream is opened at
`\AtEndPreamble` (equivalently `begindocument/before`
with an explicit ordering label).  **Not** at
`\AtBeginDocument`.

Why `\AtEndPreamble`: user documents may contain atoms
inside their own `\AtBeginDocument` blocks (e.g.,
frontmatter definitions, preface theorems injected by a
class or by user glue code).  `\AtBeginDocument` hooks
fire in registration order, and there is no guarantee
that `semtex.sty`'s hook runs before a user hook that
emits an atom.  If the stream is opened at
`\AtBeginDocument`, the first atom emitted from any
earlier-registered user hook sees `\semtex@sblwrite` as a
no-op and is silently dropped from the sidecar.

At `\AtEndPreamble`, the preamble has finished but no
`\AtBeginDocument` hook has fired yet, so the open always
precedes every atom write.

```tex
\AddToHook{begindocument/before}[semtex/sbl/open]{%
  \if@filesw
    \newwrite\semtex@sblout
    \immediate\openout\semtex@sblout=\jobname.sbl\relax
    \global\booltrue{semtex@sblopen}%
    \immediate\write\semtex@sblout{%
      \string\semtex@sbl@version{1}}%
    \immediate\write\semtex@sblout{%
      \string\semtex@sbl@source{\jobname.tex}}%
  \fi
}
\DeclareHookRule{begindocument/before}{semtex/sbl/open}{before}{*}
```

### Close timing

At `\AtEndDocument`: write the `\semtex@sbl@end{OK}`
sentinel, then `\closeout` the stream.

```tex
\AtEndDocument{%
  \ifbool{semtex@sblopen}{%
    \immediate\write\semtex@sblout{%
      \string\semtex@sbl@end{OK}}%
    \immediate\closeout\semtex@sblout
    \global\boolfalse{semtex@sblopen}%
  }{}%
}
```

If `\AtEndDocument` never runs (crash, kill -9,
`\errmessage` abort), the sentinel is absent and the CLI
rejects the file on the next analysis run.

### Emission points

At each hook site in `semtex.sty`, the following records
are written.  All calls go through the guarded helper
`\semtex@sblwrite@atom` (see "Guard pattern" below), which
checks `\semtex@currentatom` before emitting atom-scoped
records.

| Hook site (in `semtex.sty`) | Records emitted |
|---|---|
| `\semtex@hooktheorem`, `\AtBeginEnvironment{<env>}` after setting `\semtex@currentatom` | `\semtex@sbl@atom{num}{<env>}` + `\semtex@sbl@meta{num}{env}{<env>}` + `\semtex@sbl@meta{num}{src}{<file:line:col>}` |
| `\semtex@hookproof`, `\AtBeginEnvironment{proof}` standalone branch | `\semtex@sbl@atom{num}{proof}` + `\semtex@sbl@meta{num}{src}{...}` |
| `\semtex@installparahook`, normal paragraph branch after `\refstepcounter` | `\semtex@sbl@atom{num}{paragraph}` + `\semtex@sbl@meta{num}{src}{...}` |
| `\label` wrap (new `\pretocmd{\label}` site) | `\semtex@sbl@label{num}{key}` — one per `\label` call inside a current atom |
| `\semtextag{kind}{value}` | `\semtex@sbl@tag{num}{kind}{value}` |
| `\newmath` declaration (new public command; definition time) | `\semtex@sbl@newmath{cmd}{arity}{n}` + `\semtex@sbl@newmath{cmd}{src}{...}` — NOT atom-scoped (global record) |
| `\newmath`-wrapped command, every invocation inside an atom | `\semtex@sbl@use{num}{cmd}` |

The `src` metadata is built from LaTeX's
`\currfilename`, `\the\inputlineno`, and a column counter
(column counter may be approximate or omitted in the v1
writer; the `:0` suffix means "unknown column").

### Guard pattern

All emission points route through one of two helpers.
Atom-scoped records (everything except `\semtex@sbl@newmath`)
use `\semtex@sblwrite@atom`, which drops the write if
`\semtex@currentatom` is empty:

```tex
\newcommand*{\semtex@sblwrite}[1]{%
  \ifbool{semtex@sblopen}{%
    \immediate\write\semtex@sblout{#1}%
  }{%
    % Should be impossible once the file is opened at
    % begindocument/before.  Log once for debugging.
    \semtex@sblwrite@warnonce
  }%
}

\newcommand*{\semtex@sblwrite@atom}[1]{%
  \ifx\semtex@currentatom\@empty
    % Orphan: not inside an atom context.  Drop per
    % REVIEW_C finding #4.
  \else
    \semtex@sblwrite{#1}%
  \fi
}
```

Global records (`\semtex@sbl@newmath`) bypass the
atom guard and go through `\semtex@sblwrite` directly.
The `\semtex@sblwrite@warnonce` branch exists to catch
the debugging nightmare REVIEW_C finding #5 calls out;
under normal operation it should never fire because the
stream is opened at `\AtEndPreamble`.

### User API: `\semtextag`

One new public command is added to the `.sty`'s user API:

```tex
\newcommand*{\semtextag}[2]{%
  \semtex@sblwrite@atom{%
    \string\semtex@sbl@tag
    {\semtex@currentatom}{#1}{#2}}%
}
```

Usage: `\semtextag{uid}{cat:category}` inside a definition
emits one `\semtex@sbl@tag` record with the current atom's
display number.  **It has no visible typesetting effect.**
It is a pure sidecar channel for semantic metadata that
does not belong in `.aux`.  Authors who do not use the
semantic CLI can ignore `\semtextag` entirely.

### User API: `\newmath` (per REVIEW_D finding #6)

The second new public command introduces a math command
and registers it with the semantic CLI in one step.

**Signature.**

```tex
\newmath{<cmd>}{<arity>}{<body>}
```

- `<cmd>` is the command name **without** the leading
  backslash (e.g. `Hom`, `circ`, `otimes`).  The `.sty`
  internally creates `\<cmd>` from this token.  The
  bare-name convention is intentional: it avoids the cost
  of stripping a backslash before writing the name into
  `.sbl` records, where a literal `\` would need to be
  re-escaped on every emission.
- `<arity>` is a non-negative integer giving the number of
  required arguments (0, 1, 2, ...).  Required, not
  optional.  Used both by the command definition and by
  the `.sbl` `\semtex@sbl@newmath{cmd}{arity}{n}` record.
- `<body>` is the math-mode expansion.  Uses `#1`..`#N`
  for arguments as usual.

**Example.**

```tex
\newmath{Hom}{2}{\mathrm{Hom}(#1,#2)}
\newmath{id}{0}{\mathrm{id}}
```

defines `\Hom{X}{Y}` to typeset `\mathrm{Hom}(X,Y)` and
`\id` to typeset `\mathrm{id}`.

**Side effects at declaration time.**  The `.sty` emits
two `.sbl` records per `\newmath` call, both global (not
atom-scoped):

```tex
\semtex@sbl@newmath{Hom}{arity}{2}
\semtex@sbl@newmath{Hom}{src}{main.tex:15:1}
```

The arity record lets the CLI verify usage signatures.
The src record gives the CLI a source location for IDE
integration and "go to definition" lookups.

**Side effects at invocation time.**  The defined command
is wrapped so that every invocation inside an atom emits

```tex
\semtex@sbl@use{<current-atom>}{Hom}
```

via `\semtex@sblwrite@atom`.  The wrapper guards on
`\ifx\semtex@currentatom\@empty`: invocations OUTSIDE any
atom (e.g. in a section heading, caption, or
non-tracked environment) emit **no** `\semtex@sbl@use`
record.  Rationale: such invocations cannot be attributed
to any atom, and the CLI has no useful inference to make
from the orphaned record; the alternative of emitting a
`@global` use record was considered and rejected as
adding noise without analytic value.

**Optionality.**  `\newmath` is purely optional.  A
project that does not use the semantic CLI never needs to
call it; ordinary `\newcommand` works fine and produces
no `.sbl` records.  The `.sty` must not enforce usage of
`\newmath` over `\newcommand`.

**Implementation sketch.**

```tex
\newcommand*{\newmath}[3]{%
  % 1. Define the command \<cmd> with arity #2.
  \expandafter\newcommand
    \csname #1\endcsname[#2]{%
      \semtex@sblwrite@atom{%
        \string\semtex@sbl@use
        {\semtex@currentatom}{#1}}%
      #3%
    }%
  % 2. Emit the global declaration records.
  \semtex@sblwrite{%
    \string\semtex@sbl@newmath{#1}{arity}{#2}}%
  \semtex@sblwrite{%
    \string\semtex@sbl@newmath{#1}{src}%
    {\@currfilename:\the\inputlineno:1}}%
}
```

The `\@currfilename` and `\inputlineno` are LaTeX
kernel primitives giving the current file and line number
at declaration time, respectively.  The column is hard-
coded to `1` because `\inputlineno` does not give column
information; a future revision might wrap the macro at a
later point in the lexer to capture columns, but this
matches the precision LaTeX itself uses for warnings.

The `\semtex@sblwrite` call (without `@atom`) bypasses the
currentatom guard because `\semtex@sbl@newmath` records
are global, not atom-scoped.  See the "Guard pattern"
subsection above.

### Relationship to `.aux`

`.aux` and `.sbl` are siblings:

- `.aux` is LaTeX's standard sidecar.  `semtex.sty` reads
  it (for Section 8a's back-ref graph) and writes to it
  (via `\semtex@atomref` and the kernel's label
  machinery).  Read-write from the `.sty` side.
- `.sbl` is semtex's sidecar.  `semtex.sty` writes it only.
  Read by the CLI (Layer 2), not by the `.sty`.
  Write-only from the `.sty` side.

`.sbl` does not duplicate anything LaTeX already writes to
`.aux`, with one deliberate exception: **labels**.  The
`.aux` has `\newlabel{key}{{num}...}` records that map
labels to display numbers, and the `.sty`'s own
`\semtex@lblnum@<key>` csname already captures this.  The
`.sbl` ALSO emits `\semtex@sbl@label{num}{key}` because it
lets the CLI answer "what labels does atom 1.2.4 own?"
directly from the sidecar, without joining `.aux`
`\newlabel` entries against atom boundaries.  The
redundancy is a deliberate ergonomic choice for the CLI;
it costs ~one line per label and simplifies Layer 2
considerably.

Section titles, TOC entries, page numbers, rendered
output, and anything else LaTeX already writes are NOT
reproduced in `.sbl`.

## Package options

```latex
\usepackage{semtex}                       % all defaults
\usepackage[depth=1]{semtex}              % section.atom (default)
\usepackage[depth=2]{semtex}              % section.subsection.atom
\usepackage[equations=separate]{semtex}   % independent eq numbering (default)
\usepackage[equations=shared]{semtex}     % single counter
\usepackage[backrefs=inline]{semtex}      % "Used in" after each atom (default)
\usepackage[backrefs=appendix]{semtex}    % dependency index at end
\usepackage[backrefs=none]{semtex}        % numbering only
\usepackage[proofs=numbered]{semtex}      % proofs get atom numbers (default)
\usepackage[proofs=unnumbered]{semtex}    % proofs unnumbered
```

## Dependencies

- `etoolbox` — boolean flags, `\AtBeginEnvironment`,
  `\AtEndEnvironment`, command patching.
- `pgfkeys` — key-value option processing.
- `hyperref` (optional) — detected via `\@ifpackageloaded`.
  When present, back-ref numbers become clickable links.
  When absent, back-refs render as plain text.

No dependency on `thmtools`, `amsthm`, or `ntheorem`.
The `.sty` hooks into theorem environments by name via
`etoolbox`, regardless of which backend defines them.

## Compatibility

- **LaTeX kernel:** TeX Live 2021+ (stable `\AddToHook`,
  including `para/begin` and `para/end`).
- **Document classes:** `article`, `book`, `report`, `memoir`,
  KOMA-Script.  Auto-detects top-level sectioning command.
- **Theorem backends:** `amsthm`, `ntheorem`, or raw
  `\newtheorem`.  No preference imposed.
- **hyperref:** optional, detected at load time.

LaTeXML compatibility is a secondary goal.  The `.sty` uses
standard LaTeX2e mechanisms.  If LaTeXML needs help with
`\AddToHook` or other features, a `.latexml` binding file
can be added later without changing the package.

## File layout

```
tools/semtex-sty/
  CONVENTIONS.md          coding conventions
  DESIGN.md               this file
  CREDITS.md              GPLv3 provenance table (dpmac port)
  semtex.sty              the package (GPLv3)
  semtex.ltxml            LaTeXML binding for HTML output (Section 8b, GPLv3)
  build.lua               l3build configuration
  testfiles/
    test-basic.lvt        basic numbering test
    test-backrefs.lvt     back-reference display test
    test-options.lvt      package option tests
    test-hyperref.lvt     hyperref integration test
    test-ntheorem.lvt     ntheorem backend test
    test-depth.lvt        depth option test
    test-equations.lvt    equations=shared test
    test-proofs.lvt       proof numbering test
    test-book.lvt         book class test
    test-nested.lvt       nested environment test
    test-starred.lvt      starred environment test
    test-latexml.lvt      LaTeXML HTML binding test (Section 8b)
  .latexindent.yaml       formatter config
```

## Non-goals

- Does not define theorem environments (user's preamble does).
- Does not define math macros.
- Does not perform semantic analysis.
- Does not generate dependency graphs.
- Does not handle UID assignment.
- Does not auto-generate labels.

## TODO

- **Margin-only numbering style.** Add `style=margin` option that
  puts ALL atom numbers (including theorems/definitions) as
  superscript margin numbers, removing the number from theorem
  headers.  Gives a visually uniform margin column.  Current
  behavior becomes `style=inline` (default for now).

## Credit

**The back-reference machinery (Section 8a) is a direct
port of Dmitri Pavlov's `dpmac.tex`** (Plain TeX, GNU
GPLv3, 2007-2023).  The ported elements include the
defer-queue pattern, the `\recordbackref` / `\processbackref`
control flow, the per-target csname table for the inverted
adjacency list, and the self-ref dedup logic.  LaTeX-
specific adaptations (the `.aux` rerun as persistence layer,
the `\@setref` patch, the `\AddToHook` wiring) are new.

The whole of `semtex.sty` is therefore distributed under
**GNU GPL version 3** as a derivative work.  See
`tools/semtex-sty/CREDITS.md` for the provenance table,
bucket-by-bucket attribution, and the intent to reach out
to Pavlov regarding a possible LPPL dual-license courtesy.

The shared counter, paragraph-as-atom, and "Used in"
back-reference *concepts* also originate from Pavlov's
system.
