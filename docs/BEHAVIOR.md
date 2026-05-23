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
| `backref-style` | `inline` | `inline` | Rendering style for "Used in" |
| `backref-font` | any font command | `\scriptsize\sffamily` | Font for "Used in" text |
| `backref-color` | color name | (none) | Color for "Used in" text (requires xcolor) |
| `backref-prefix` | text | (empty) | Text before "Used in" |
| `backref-label` | text | `Used in` | Label text before the ref list |
| `margin-font` | any font command | `\scriptsize` | Font for margin atom numbers |

**Note**: `backref-style=below` and `backref-style=margin` were removed in v2.0. To place backreferences in custom positions, use `\codepbackrefs` in a custom `\newtheoremstyle` endmark (see `docs/COOKBOOK.md`).

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
\begin{proof}[\codepproofof{label}]   % bind a separated proof to label
\begin{proof}[\codepproofof*{label}]  % compatibility alias for the same path
```

- Associates a separated proof with its theorem via label lookup.
- The proof's backrefs display as `X*` where X is the theorem's number.
- Backrefs to that proof resolve to the proof heading via the proof key's `\codep@anchormap` entry, not the theorem heading.
- The starred form is retained for compatibility; both forms alias to the same proof-begin anchor path.
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
- Entries grouped by section, with hanging-indent rows and leader dots.
- Format: `Kind N (p. P) ...... ref1, ref2, ref3` (the page-number segment is configurable via `/codep/appendix/pagenum-format`).

---

## 3. Observable Behavior

### 3.1 Atom numbering

| Property | Behavior |
|---|---|
| [B-NUM-SHARED] Shared counter | One counter for tracked environments + paragraphs only; standalone proofs do NOT consume a slot (their key uses an opaque proof-id) |
| [B-NUM-DEPTH1] Display format (`depth=1`) | `section.N` (article) or `chapter.N` (book/report) |
| [B-NUM-DEPTH2] Display format (`depth=2`) | `section.subsection.N` or `chapter.section.N` |
| [B-NUM-RESET] Counter reset | Resets at the deepest sectioning level in the display |
| [B-NUM-SEQ] Sequential | All tracked envs share one counter: Def 1.1, Thm 1.2, Lem 1.3, ... |
| [B-NUM-PARA] Paragraphs | Superscript margin number (left margin) when `paragraphs=on` |
| [B-NUM-EQINDEP] Equations | Independent counter; never shares the atom counter |
| [B-NUM-STARRED] Starred envs | `theorem*` gets an atom number (same counter) |
| [B-NUM-NESTED] Nested tracked envs | Inner env suppressed; outer env's number covers both |

### 3.2 Back-reference display

When atom A contains `\ref{B}` (or `\cref`, `\autoref`, etc.), atom B
displays "Used in A" in the PDF.

**Display format by source type:**

| Source type | Display | Example |
|---|---|---|
| [B-DISP-THM] Theorem/definition/etc. | bare number | `2.1` |
| [B-DISP-PROOF] Proof (adjacent) | starred | `2.1*` |
| [B-DISP-EQ] Equation (standalone) | parenthesized | `(3)` |
| [B-DISP-EQRANGE] Equation (align range) | parenthesized range | `(3--5)` |
| [B-DISP-PARA] Paragraph | bare number | `2.1` |

**Rendering modes:**

| Mode | Where it appears | Layout |
|---|---|---|
| [B-REND-INLINE] `inline` (default) | End of the atom body, same line as content | `...text. Used in 2.1, 3.4.` |
| [B-REND-APPENDIX] `appendix` | Collected in dependency index | Via `\codepappendix` |

`backref-style=below` and `backref-style=margin` were removed in v2.0.  Use `\codepbackrefs` inside a custom `\newtheoremstyle` endmark to place the backref wherever the theorem style prefers; see `docs/COOKBOOK.md`.

- [B-DEDUP] **Deduplication:** Multiple `\ref`s from the same source to the same target produce one backref entry.

- [B-SELFREF] **Self-reference:** `\ref` to the containing atom is not recorded as a backref.

- [B-ZERO-REF] **Zero inbound refs:** No "Used in" annotation appears.

- [B-REND-BACKREFSOF] **Remote Used-In read:** `\codepbackrefsof{label}` renders the Used-In list for the tracked codependent atom identified by `label`, without marking that atom manually emitted. The `label` argument is a tracked codependent atom label. Arbitrary non-tracked LaTeX labels (e.g. `sec:intro`) fall through to the warning path. Forward refs warn on the first pass and emit on subsequent passes (depends on `\codep@lblentity@<label>` from a previous run's `.aux`).

### 3.3 Hyperlinks

- [B-LINK-CLICKABLE] When hyperref is loaded, every entry in "Used in X, Y" is a clickable link.
- *(retired: `B-LINK-CORRECT` — umbrella for the four rows below; specialise tests to B-LINK-EFFECTIVE-ANCHOR / B-LINK-PROOF-DEST / B-LINK-PROOFOF-STAR / B-LINK-ADJ-PROOF.)*
- [B-LINK-EFFECTIVE-ANCHOR] For theorem-like atoms, backlink destinations resolve from the effective anchor: the heading anchor, possibly replaced by a same-typed same-display in-atom label. Proof and appendix links are routed through their own anchor maps rather than borrowing the theorem anchor.
- [B-LINK-PROOF-DEST] Proof backlinks are addressable through `\codep@anchormap`. Adjacent, rebound, and standalone proofs all bind their canonical opaque `proof:a<N>` key through `\codep@anchormap` to the proof-begin anchor. The physical hyperref destination names are not part of the public contract.
- [B-PROOF-ANCHOR-NEAR-HEADING] Adjacent, standalone, and rebound proofs all place exactly one proof-local anchor at proof-begin, so proof backlinks land near the rendered proof heading, not after the proof or on a later in-proof equation anchor.
- [B-LINK-PROOFOF-STAR] Both `\codepproofof` and `\codepproofof*` bind separated proofs to the proof's own anchor; the starred form is retained as an explicit compatibility spelling for the same proof-begin aliasing path.
- [B-LINK-ADJ-PROOF] Backref entries for adjacent proofs resolve through the adjacent proof's own `\codep@anchormap` target, not the parent theorem anchor. Effective-anchor rewrites on the parent theorem do not collapse the proof backlink onto the theorem target.
- [B-LINK-APPENDIX-BIDIR] In `backrefs=appendix` mode, links are bidirectional: a dagger marker emitted with the body-side backref rail links forward to `codep-appendix:<key>`, and each appendix entry label links back to the atom's effective body anchor. Proof-source entries within appendix rows resolve through the proof key's `\codep@anchormap` target.
- [B-LINK-NO-ORPHAN] No orphan links: every link resolves to a valid PDF destination.

### 3.4 Equation tracking

| Mode | Equations outside theorems | Equations inside theorems |
|---|---|---|
| [B-EQ-OUTER] `outer` (default) | Tracked as backref sources | Fall through to containing theorem |
| [B-EQ-ALL] `all` | Tracked as backref sources | Tracked as backref sources |
| [B-EQ-OFF] `off` | Not tracked | Not tracked |

- [B-EQ-TRACK1] **Track 1 (single-number):** `equation` -- displays as `(N)`.

- [B-EQ-TRACK2] **Track 2 (multi-number):** `align`, `gather`, `multline`, `flalign` -- displays as `(N--M)` range.

**Edge cases:**
- [B-EQ-NOTAG] All-`\notag` align: no equation tracking; falls through to containing atom or silently dropped.
- [B-EQ-SUBEQ] `\subequations` wrapping align: range uses subeq format, e.g. `(1a--1c)`.
- [B-EQ-UNNUM] Unnumbered envs (`equation*`, `align*`, etc.): no tracking, paragraph suppression only.

### 3.5 Proof attribution

| Situation | Atom identity | Display in backrefs |
|---|---|---|
| [B-PROOF-ADJ] Adjacent proof (directly after a tracked env) | Inherits the parent atom's number | `2.1*` |
| [B-PROOF-SEP] Separated proof via `\codepproofof{label}` | Inherits target's number; bidirectional: the target's "Used in" shows `N.M*`, and `N.M*` entries in other atoms' backref lists resolve through the proof's `\codep@anchormap` target | `2.1*` |
| [B-PROOF-NONADJ] Non-adjacent proof (no `\codepproofof`) | Opaque proof-id key (`proof:a<N>`); does not consume a shared-counter slot; warning emitted | suppressed from source-token output |
| [B-PROOF-INNER] Proof inside a tracked env | Suppressed (part of outer atom) | N/A |
| [B-PROOF-OFF] `proofs=off` | No atom number, paragraph suppression only | N/A |
| [B-PROOF-OPAQUE-ID] Proof atom identity | Every proof atom uses a stable opaque key of the form `proof:a<N>` in `.aux` / `.cdp` records and `\codep@anchormap`; display-number keys such as `proof:1.2` or `proof:{1.1,1.2}` are not emitted. Covered by the `integ-proofauto-*` fixtures. |
| [B-PROOF-JOINT] Joint proof attribution | A single proof heading that references multiple tracked targets is represented as one proof atom whose displayed source token is the braced target list with `*`, e.g. `{1.1, 1.2}*`, and that one atom appears consistently in inline and appendix backrefs. Covered by `integ-proofauto-joint-atom.lvt`. |
| [B-PROOF-HEADING-OVERRIDE] Heading target overrides adjacency | When a proof is physically adjacent to one tracked atom but its heading names a different tracked target, the heading target receives the proof attribution and the adjacent atom is not polluted with the proof backref. Covered by `integ-proofauto-d3-heading-overrides-adjacent.lvt`. |
| [B-WARN-ATTR-CONFLICTS] Attribution conflict warning toggle | `warn-attribution-conflicts=false` suppresses only the warning for a heading-target-over-adjacent-target conflict; it does not change the attribution result. Covered by `integ-proofauto-d3-heading-overrides-adjacent.lvt`. |
| [B-PROOF-DELAYED-COMMIT] Delayed adjacent proof commit | Adjacent proof candidates are staged while the proof heading is scanned, then committed only after heading attribution has had a chance to override or drop the adjacent candidate. Covered by `integ-proofauto-adjacent-delayed-commit-probe.lvt` and `integ-proofauto-adjacent-no-leak.lvt`. |
| [B-PROOF-UNRESREF] Forward proof-heading resolution | A proof heading that names a tracked label not yet defined in the current run is routed through an `unresref:<N>` placeholder and resolves to the later target on the convergence pass without emitting display-keyed proof aliases. Covered by `integ-proofauto-forward-ref.lvt`. |

- [B-PROOF-ADJRULE] **Adjacency rule:** Auto-attribution fires whenever a tracked environment closes with no intervening paragraph or other tracked environment before the proof opens. Any `\codeptrack`-registered environment is eligible, not just result-type environments like `theorem`, `lemma`, `proposition`, `corollary`.

### 3.6 Concept tracking

- [B-CONC-EDGES] `\codepnewcommand`-defined commands produce concept-use edges in the backref graph.
- [B-CONC-USEDIN] All uses (`\cmd`) of a concept appear as "Used in" entries on the def-site atom.
- [B-CONC-DEFSITE] The def site is marked by `\cmd*`; exactly one per concept.
- [B-CONC-SCOPE] Concept edges are observation-layer records: they are written to `.aux`/`.cdp` for hyperlink resolution and CLI graph consumers, but are NOT injected into PDF "Used in" lists.
- [B-CONC-FWDREF] Forward references (use before def) are resolved on pass 2.
- [B-CONC-NODEF] Missing def site: warning; concept backrefs disabled for that command.
- [B-CONC-DUPDEF] Duplicate def site: error; build halts.
- [B-CONC-OUTSIDE] Invocations outside any atom (headings, captions, footnotes): silently ignored.

### 3.7 Suppression

Paragraph numbers are suppressed inside:

| Category | Environments / commands |
|---|---|
| [B-SUPP-LISTS] Lists | `enumerate`, `itemize`, `description` |
| [B-SUPP-QUOTE] Quoting | `quote`, `quotation` |
| [B-SUPP-FLOATS] Floats | `figure`, `table` |
| [B-SUPP-BOXES] Boxes | `minipage`, `\parbox`, `tcolorbox` |
| [B-SUPP-WRAPPERS] Kernel align wrappers | `center`, `flushleft`, `flushright`, `verbatim` (paragraphs typeset by these `\trivlist`-based wrappers are not numbered) |
| [B-SUPP-TABLES] Tables | `tabular`, `tabularx`, `longtable` |
| [B-SUPP-MATH] Math display | `equation(*)`, `align(*)`, `gather(*)`, `multline(*)`, `flalign(*)`, `displaymath` |
| [B-SUPP-TRACKED] Tracked envs | All environments registered via `\codeptrack` |
| [B-SUPP-CMDS] Commands | `\footnote`, `\parbox`, `\maketitle` |
| [B-SUPP-SECTION] Sectioning | `\section`, `\subsection`, etc. (heading paragraph only) |

- [B-SUPP-EXTEND] User-extensible via `\codepsuppress{env}` and `\codepsuppresscmd{\cmd}`.

### 3.8 Restatable support

- [B-REST-FIRST] `\begin{restatable}{theorem}{TheoremCmd}...\end{restatable}` works normally (first occurrence gets the atom).
- [B-REST-NODUP] `\TheoremCmd*` (restate) does NOT create a duplicate atom or backref entries.
- [B-REST-CONCEPT] Concept commands (`\cmd*`) inside a restated body register the def site only at the original declaration, not at the restate site.

### 3.9 `.cdp` sidecar-format rail (`BCDP-*`)

These IDs document `.cdp` wire-format invariants observed by the
`codep` CLI consumer.  They are NOT user-PDF behaviors — the `B-*`
prefix is reserved for that.  A `BCDP-*` ID is honest only if a
real `.sty` macro emits the record being asserted.

- [BCDP-VERSION] The first non-comment record in `.cdp` is `\codep@cdp@version{<n>}` carrying the current schema version. Emitted from the `begindocument/before` open hook in `codependent.sty`.
- [BCDP-SOURCE] The second non-comment record is `\codep@cdp@source{<file>}` naming the source document. Emitted alongside `BCDP-VERSION` from the open hook.
- [BCDP-SENTINEL] The final record before `\endinput` is `\codep@cdp@end{OK}` confirming a clean drain. Emitted by `\codep@enddoc@drain@sentinel` (sentinel drain slot, runs last so the closeout cannot drop later writes).
- [BCDP-FLAT-RECORD] User-emitted tag records use the fixed 3-arg flat shape `\codep@cdp@tag{atom}{kind}{value}` (NOT key-value blobs in a single argument). Emitted by `\codeptag{kind}{value}`.

---

## 4. Package Interactions

| Package | Status | Notes |
|---|---|---|
| amsthm | Required (or ntheorem) | Theorem backend; load before codependent |
| hyperref | Optional | Enables clickable backref links; use `hypertexnames=false` |
| cleveref | Optional | `\cref`, `\Cref`, etc. fully tracked as backref sources |
| thmtools | Optional | `sibling=`, `restatable`, custom styles all work |
| [B-COMPAT-THMTOOLS-CONTINUED] thmtools continued theorems | Optional | `[continued=...]` theorem instances are tracked through the same generic `\codeptrack` begin/end hook surface as ordinary theorem instances; no thmtools-specific shim is required. Covered by `integ-thmtools-continued-generic-hooks.lvt`. |
| amsmath | Optional | Equation environments auto-tracked |
| subfiles / standalone | Compatible | Multi-file projects work; canonical build from master doc |
| article, book, report, KOMA | Supported | Auto-detects `\chapter` for depth formatting |

**Reference commands tracked:** `\ref`, `\eqref`, `\cref`, `\Cref`, `\autoref`, `\ref*`, `\Ref`, `\vref`, `\nameref`, `\labelcref`, `\labelcref*`, `\crefrange`, and all cleveref family commands.

**Deliberately NOT tracked:** `\hyperref[label]{text}` (manual link, not a semantic reference).

---

## 5. Two-Pass Behavior

| Pass | What happens | What the user sees |
|---|---|---|
| [B-PASS-ONE] Pass 1 | Atoms numbered, references recorded, and same-run label-number / effective-anchor state hydrated from `\label` | Correct numbering; NO "Used in" annotations |
| [B-PASS-TWO] Pass 2 | Reference graph inverted and backrefs rendered from already-final targets/links | Full "Used in" annotations with final links |

*(retired: `B-PASS-SINGLE`, `B-PASS-RERUN`, `B-PASS-THREE` — emergent properties of the LaTeX kernel and the B-PASS-ONE/B-PASS-TWO pair, not codependent macro behaviors. Single-pass numbering and rerun-on-label-change are kernel behaviors; the cold-pass-floor invariant is a suite-level convergence contract tested via integration fixtures, not a macro carrier.)*

### 5.1 End-of-document finalization

At `\end{document}` a single orchestrator evaluates per-subsystem
operation counters (`proofof`, `atomref`, `label-bind`, `backref-render`)
and dispatches to a fixed-order drain pipeline.

- [B-ERROR-ENDDOC] **Fatal finalization error:** when every operation in at least one subsystem failed (failed-count equals total-count and total-count > 0), the orchestrator skips all drains and emits `\PackageError`; the `.aux` and `.cdp` files are NOT updated with stale records, so a subsequent retry sees a clean prior run.
- [B-WARN-ENDDOC] **Partial-failure warning:** when some but not all operations in a subsystem failed (0 < failed < total), drains run normally and the orchestrator emits one `\PackageWarning` per affected subsystem naming the failed/total count.

---

## 6. Edge Cases and Expected Behavior

| Scenario | Expected outcome |
|---|---|
| [B-EDGE-ZERO-REF] Atom with zero inbound refs | No "Used in" annotation |
| [B-EDGE-DEDUP] Multiple `\ref` to same target from one atom | Single backref entry (deduplicated) |
| [B-EDGE-HEADING] `\ref` in section heading | Not attributed to any atom; no backref recorded |
| [B-EDGE-FOOTNOTE] `\ref` in footnote | Not attributed to any atom (suppressed context) |
| [B-EDGE-NESTED] Nested tracked environments | Inner env suppressed; no separate atom number |
| [B-EDGE-PROOF-ANY] Proof after any tracked env (including definition, remark) | Adjacent; inherits parent number with * |
| [B-EDGE-NOTAG] All-`\notag` align block | No equation tracking; falls through to containing atom |
| [B-EDGE-EMPTY-PROOF] Empty proof (no body content) | Adjacent: inherits parent's number with `*`. Standalone: opaque proof-id key, no shared-counter slot, suppressed from source-token output (per B-PROOF-NONADJ) |
| [B-EDGE-BADLABEL] `\codepproofof` with invalid label | Warning; falls through to standalone materialization (opaque proof-id key, no shared-counter slot, suppressed from source-token output, per B-PROOF-NONADJ) |
| [B-EDGE-TRACK-TWICE] `\codeptrack` called twice | Error: "codeptrack called twice" |
| [B-EDGE-TRACK-ORDER] `\codeptrack` before `\newtheorem` | Error: counter undefined |
| [B-EDGE-CONC-OUTSIDE] `\codepnewcommand` cmd used in caption/heading | No concept record (outside atom context) |
| [B-EDGE-RESTATE] Restated theorem refire | No duplicate atom; restate body is inert for tracking |
| [B-EDGE-PARAOFF-EQ] `paragraphs=off` + standalone equation | Equation tracked normally if `equations=outer` or `all` |
| [B-EDGE-MULTI-SAME] Same atom references same target multiple times | Deduplicated; single backref entry |
| [B-EDGE-HYPERREF] `\hyperref[label]{text}` inside an atom | Link rendered but NO backref edge recorded |
| [B-FRONTEDGE-CAPTURE] Front-edge ref capture | `\ref`, `\pageref`, `\Ref`, `\cref`, `\Cref`, `\autoref`, `\labelcref` (and `*` variants) emit `\codep@atomref` records on every pass, including pass 1 when the target is unresolved (`??`). Wrappers are installed at `begindocument/end` after nameref/hyperref/cleveref settle. `\crefrange`, `\Crefrange`, `\nameref`, `\nameref*` are waived (no front-edge wrapper). |
| [B-FRONTEDGE-DEDUP-EQ] Front-edge track-two dedup | Inside multiline equation environments (`align`, `gather`, etc.), each `(source, target)` pair is enqueued at most once per equation block. The guard `\codep@arw@pending@<tgt>` is retained as belt-and-braces after the backend wrappers were removed, so multiline refs still cannot double-enqueue. |
