# codependent.sty -- Behavioral Specification

## 1. Purpose

codependent is a LaTeX package that assigns sequential numbers to every
theorem, definition, proof, and paragraph in a mathematical document,
tracks which atoms reference which, and renders "Used in X, Y, Z"
back-reference annotations in the PDF. Two pdflatex runs produce the
final output; no external tools are required.

---

## 2. User-Facing API

### 2.1 Package loading and options

```latex
\usepackage[<options>]{codependent}
```

Load **after** the theorem backend (amsthm/ntheorem) and **after** all
`\newtheorem` / `\declaretheorem` declarations.

| Option | Values | Default | Effect |
|---|---|---|---|
| `depth` | `1`, `2`, `3` | `1` | Sectioning levels in atom display numbers |
| `backrefs` | `inline`, `appendix`, `none` | `inline` | Back-reference display mode |
| `proofs` | `on`, `off` | `on` | Whether proofs get atom numbers |
| `proof-warnings` | `on`, `off` | `on` | Warn on non-adjacent proofs |
| `paragraphs` | `on`, `off` | `on` | Whether bare paragraphs get atom numbers |
| `equations` | `outer`, `all`, `off` | `outer` | Equation backref tracking mode |
| `conceptwarnings` | `on`, `off` | `on` | Warn on missing `\cmd*` def sites |
| `backref-style` | `inline`, `below`, `margin` | `inline` | Rendering style for "Used in" |
| `backref-align` | `left`, `right` | `right` | Alignment of "Used in" in below mode |
| `backref-font` | any font command | `\scriptsize\sffamily` | Font for "Used in" text |
| `backref-color` | color name | (none) | Color for "Used in" text (requires xcolor) |
| `backref-prefix` | text | (empty) | Text before "Used in" |
| `backref-label` | text | `Used in` | Label text before the ref list |
| `backref-margin-max` | integer | `5` | Max refs in margin mode before truncation |
| `margin-font` | any font command | `\scriptsize` | Font for margin atom numbers |

### 2.2 \codeptrack

```latex
\codeptrack{env1,env2,...}
```

- **Call once**, after all `\newtheorem` declarations.
- Registers the listed environments for atom numbering and back-reference tracking.
- Starred variants (e.g. `theorem*`) are auto-registered.
- The first environment's counter becomes the shared atom counter.
- Also activates proof tracking, paragraph numbering, and suppression.

### 2.3 \codepsetup

```latex
\codepsetup{key=value,...}
```

- Reconfigure any package option at any point (preamble or body).
- Same keys as package options.

### 2.4 \codeptag

```latex
\codeptag{kind}{value}
```

- Attaches semantic metadata to the current atom.
- **No visible effect in the PDF.** Metadata goes to the `.cdp` sidecar only.
- Ignored outside a tracked atom.
- Example: `\codeptag{uid}{cat:enriched-category}`

### 2.5 \codepproofof / \codepproofof*

```latex
\begin{proof}[\codepproofof{label}]   % link "Used in X*" -> theorem
\begin{proof}[\codepproofof*{label}]  % link "Used in X*" -> proof location
```

- Associates a separated proof with its theorem via label lookup.
- The proof's backrefs display as `X*` where X is the theorem's number.
- Starred form: clicking the backref jumps to the proof, not the theorem.
- Warning if label is undefined.
- Must be called inside `\begin{proof}...\end{proof}`.

### 2.6 \codepnewcommand

```latex
\codepnewcommand{\cmd}[arity]{body}
```

- Defines `\cmd` with concept tracking. Mirrors `\newcommand` exactly.
- `\cmd{args}` = use site. Typesets the body; records concept usage.
- `\cmd*{args}` = def site. Typesets identically; marks the defining atom.
- Exactly one `\cmd*` per concept. Zero `\cmd*` + any `\cmd` = warning. Two `\cmd*` = error.
- Example:
  ```latex
  \codepnewcommand{\Hom}[2]{\mathrm{Hom}(#1,#2)}
  % In a definition: $\Hom*{X}{Y}$ is defined as...  (def site)
  % Elsewhere:       $\Hom{A}{B}$                    (use site)
  ```

### 2.7 \codepNewDocumentCommand

```latex
\codepNewDocumentCommand{\cmd}{argspec}{body}
```

- Same concept tracking as `\codepnewcommand`, using xparse argument syntax.
- Star dispatch prepended to user's argspec; `\cmd*` = def site, `\cmd` = use site.

### 2.8 \codeptrackeq / \codeptrackalign

```latex
\codeptrackeq{envname}      % custom single-number equation env (Track 1)
\codeptrackalign{envname}   % custom multi-number equation env (Track 2)
```

- Register custom equation environments for backref tracking.
- Standard environments (`equation`, `align`, `gather`, `multline`, `flalign`) are auto-registered.

### 2.9 \codepsuppress / \codepsuppresscmd

```latex
\codepsuppress{envname}     % suppress paragraph numbers inside envname
\codepsuppresscmd{\cmd}     % suppress paragraph numbers inside \cmd's body
```

- Extends the built-in suppression list.

### 2.10 \codepappendix

```latex
\codepappendix
```

- Typesets a "Dependency Index" section listing every atom with its back-references.
- Only functional when `backrefs=appendix`.
- Entries grouped by section, with dotfill leaders.
- Format: `number  type  ......  ref1, ref2, ref3`

---

## 3. Observable Behavior

### 3.1 Atom numbering

| Property | Behavior |
|---|---|
| Shared counter | One counter for all tracked environments + paragraphs + proofs |
| Display format (`depth=1`) | `section.N` (article) or `chapter.N` (book/report) |
| Display format (`depth=2`) | `section.subsection.N` or `chapter.section.N` |
| Counter reset | Resets at the deepest sectioning level in the display |
| Sequential | All tracked envs share one counter: Def 1.1, Thm 1.2, Lem 1.3, ... |
| Paragraphs | Superscript margin number (left margin) when `paragraphs=on` |
| Equations | Independent counter; never shares the atom counter |
| Starred envs | `theorem*` gets an atom number (same counter) |
| Nested tracked envs | Inner env suppressed; outer env's number covers both |

### 3.2 Back-reference display

When atom A contains `\ref{B}` (or `\cref`, `\autoref`, etc.), atom B
displays "Used in A" in the PDF.

**Display format by source type:**

| Source type | Display | Example |
|---|---|---|
| Theorem/definition/etc. | bare number | `2.1` |
| Proof (adjacent) | starred | `2.1*` |
| Equation (standalone) | parenthesized | `(3)` |
| Equation (align range) | parenthesized range | `(3--5)` |
| Paragraph | bare number | `2.1` |

**Rendering modes:**

| Mode | Where it appears | Layout |
|---|---|---|
| `inline` (default) | End of the atom body, same line as content | `...text. Used in 2.1, 3.4.` |
| `below` | Separate line after the atom | Right- or left-aligned per `backref-align` |
| `margin` | Right margin | Small text past line width |
| `appendix` | Collected in dependency index | Via `\codepappendix` |

**Deduplication:** Multiple `\ref`s from the same source to the same target produce one backref entry.

**Self-reference:** `\ref` to the containing atom is not recorded as a backref.

**Zero inbound refs:** No "Used in" annotation appears.

### 3.3 Hyperlinks

- When hyperref is loaded, every entry in "Used in X, Y" is a clickable link.
- Link targets point to the correct atom's location in the PDF.
- `\codepproofof*` overrides the link target to point to the proof location.
- Adjacent proofs link to the theorem's location (they share its identity).
- No orphan links: every link resolves to a valid PDF destination.

### 3.4 Equation tracking

| Mode | Equations outside theorems | Equations inside theorems |
|---|---|---|
| `outer` (default) | Tracked as backref sources | Fall through to containing theorem |
| `all` | Tracked as backref sources | Tracked as backref sources |
| `off` | Not tracked | Not tracked |

**Track 1 (single-number):** `equation` -- displays as `(N)`.

**Track 2 (multi-number):** `align`, `gather`, `multline`, `flalign` -- displays as `(N--M)` range.

**Edge cases:**
- All-`\notag` align: no equation tracking; falls through to containing atom or silently dropped.
- `\subequations` wrapping align: range uses subeq format, e.g. `(1a--1c)`.
- Unnumbered envs (`equation*`, `align*`, etc.): no tracking, paragraph suppression only.

### 3.5 Proof attribution

| Situation | Atom identity | Display in backrefs |
|---|---|---|
| Adjacent proof (directly after a tracked result env) | Inherits theorem's number | `2.1*` |
| Separated proof with `\codepproofof{label}` | Inherits target's number | `2.1*` |
| Non-adjacent proof (no `\codepproofof`) | Gets own atom number + warning | `3.5` |
| Proof inside a tracked env | Suppressed (part of outer atom) | N/A |
| `proofs=off` | No atom number, paragraph suppression only | N/A |

**Adjacency rule:** Auto-attribution fires only when nothing (no paragraph, no other tracked env) intervenes between a result-type environment and the proof.

**Result-type environments** (eligible for auto-attributed proofs): `theorem`, `lemma`, `proposition`, `corollary` (and any registered via `results`).

### 3.6 Concept tracking

- `\codepnewcommand`-defined commands produce concept-use edges in the backref graph.
- All uses (`\cmd`) of a concept appear as "Used in" entries on the def-site atom.
- The def site is marked by `\cmd*`; exactly one per concept.
- Concept edges do NOT appear in "Used in" lists of referenced atoms -- they appear only on the definition atom.
- Forward references (use before def) are resolved on pass 2.
- Missing def site: warning; concept backrefs disabled for that command.
- Duplicate def site: error; build halts.
- Invocations outside any atom (headings, captions, footnotes): silently ignored.

### 3.7 Suppression

Paragraph numbers are suppressed inside:

| Category | Environments / commands |
|---|---|
| Lists | `enumerate`, `itemize`, `description` |
| Quoting | `quote`, `quotation` |
| Floats | `figure`, `table` |
| Boxes | `minipage`, `\parbox` |
| Tables | `tabular`, `tabularx`, `longtable` |
| Math display | `equation(*)`, `align(*)`, `gather(*)`, `multline(*)`, `flalign(*)`, `displaymath` |
| Tracked envs | All environments registered via `\codeptrack` |
| Commands | `\footnote`, `\parbox`, `\maketitle` |
| Sectioning | `\section`, `\subsection`, etc. (heading paragraph only) |

User-extensible via `\codepsuppress{env}` and `\codepsuppresscmd{\cmd}`.

### 3.8 Restatable support

- `\begin{restatable}{theorem}{TheoremCmd}...\end{restatable}` works normally (first occurrence gets the atom).
- `\TheoremCmd*` (restate) does NOT create a duplicate atom or backref entries.
- Concept commands (`\cmd*`) inside a restated body register the def site only at the original declaration, not at the restate site.

---

## 4. Package Interactions

| Package | Status | Notes |
|---|---|---|
| amsthm | Required (or ntheorem) | Theorem backend; load before codependent |
| hyperref | Optional | Enables clickable backref links; use `hypertexnames=false` |
| cleveref | Optional | `\cref`, `\Cref`, etc. fully tracked as backref sources |
| thmtools | Optional | `sibling=`, `restatable`, custom styles all work |
| amsmath | Optional | Equation environments auto-tracked |
| subfiles / standalone | Compatible | Multi-file projects work; canonical build from master doc |
| article, book, report, KOMA | Supported | Auto-detects `\chapter` for depth formatting |

**Reference commands tracked:** `\ref`, `\eqref`, `\cref`, `\Cref`, `\autoref`, `\ref*`, `\Ref`, `\vref`, `\nameref`, `\labelcref`, `\crefrange`, and all cleveref family commands.

**Deliberately NOT tracked:** `\hyperref[label]{text}` (manual link, not a semantic reference).

---

## 5. Two-Pass Behavior

| Pass | What happens | What the user sees |
|---|---|---|
| Pass 1 | Atoms numbered, references recorded | Correct numbering; NO "Used in" annotations |
| Pass 2 | Reference graph inverted, backrefs rendered | Full "Used in" annotations with links |

- A single-pass build produces a correctly numbered document without backrefs.
- "Rerun needed" = labels changed; standard LaTeX `Label(s) may have changed` warning.
- Three runs needed when labels are newly created (first run establishes labels, second reads them, third stabilizes backrefs).

---

## 6. Edge Cases and Expected Behavior

| Scenario | Expected outcome |
|---|---|
| Atom with zero inbound refs | No "Used in" annotation |
| Multiple `\ref` to same target from one atom | Single backref entry (deduplicated) |
| `\ref` in section heading | Not attributed to any atom; no backref recorded |
| `\ref` in footnote | Not attributed to any atom (suppressed context) |
| Nested tracked environments | Inner env suppressed; no separate atom number |
| Proof after any tracked env (including definition, remark) | Adjacent; inherits parent number with * |
| All-`\notag` align block | No equation tracking; falls through to containing atom |
| Empty proof (no body content) | Still gets an atom number |
| `\codepproofof` with invalid label | Warning; proof becomes standalone with own number |
| `\codeptrack` called twice | Error: "codeptrack called twice" |
| `\codeptrack` before `\newtheorem` | Error: counter undefined |
| `\codepnewcommand` cmd used in caption/heading | No concept record (outside atom context) |
| Restated theorem refire | No duplicate atom; restate body is inert for tracking |
| `paragraphs=off` + standalone equation | Equation tracked normally if `equations=outer` or `all` |
| Same atom references same target multiple times | Deduplicated; single backref entry |
| `\hyperref[label]{text}` inside an atom | Link rendered but NO backref edge recorded |
