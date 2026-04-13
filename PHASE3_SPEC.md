# Phase 3: Graph Redesign --- Implementation Specification

## 1. Overview

The graph redesign replaces codependent's current `type:displaynumber` identity model (e.g. `theorem:1.2`, `equation:1--2`) with opaque monotone IDs (`a1`, `a2`, ... for source atoms; `q1`, `q2`, ... for equation-label targets), adds an explicit global source-context stack to replace the brittle mix of `\codep@currentatom`/`\codep@sourceatom`/`\codep@nestlevel`/`\ifcodep@intheorem` flags, introduces a rendering query API that fully decouples `codependent-render.sty` from graph internals, upgrades both the `.aux` protocol and `.cdp` sidecar to use entity-ID-based records, and makes numbered equation environments source-capable atoms while keeping each equation label as its own distinct target. The migration proceeds in five waves, each of which leaves the full test suite green.

## 2. Target Architecture

### 2.1 Identity Model

Two ID spaces, both global monotone counters:

| Space | Prefix | What it identifies | Source-capable? |
|-------|--------|--------------------|-----------------|
| `a` | `\codep@atomid` | Paragraphs, tracked theorem-like envs, proofs, source-capable equation envs | Yes |
| `q` | `\codep@targetid` | Individual equation labels (one per `\label` inside a numbered display) | No |

**Key rules:**
- Atom identity is `aN` only. Display strings (`2.3`, `(1--3)`) are metadata; changing them does not change identity.
- Equation labels are distinct targets even when they share one display block. `\label{eq:a}` and `\label{eq:b}` in the same `align` map to different `qK` IDs.
- Graph edges are always `source-atom-id -> target-entity-id`.
- Dedup is by resolved pair `(source-atom-id, target-entity-id)`, not by label text.
- For a fixed source and configuration, ID allocation is reproducible. Edits or option changes can renumber later IDs and require normal LaTeX reruns.
- `\codepproofof` never changes a proof atom's ID; it only changes proof metadata.

### 2.2 Runtime State

All semantic state is explicit and global. No semantic state depends on TeX group unwinding.

```tex
\newcount\codep@atomid          % monotone source atom counter
\newcount\codep@targetid        % monotone equation-label target counter
\newcount\codep@ctxdepth        % source-context stack depth
\newcount\codep@suppressdepth   % paragraph suppression depth
\newcount\codep@trackeddepth    % tracked-env nesting depth
\newcount\codep@replaydepth     % restatable replay depth

\newif\ifcodep@paragraphopen    % is a paragraph atom currently open?
\newif\ifcodep@proofdisplaypending % current proof only: display not yet assigned

\newcommand*\codep@pendingresultid{}   % last adjacent proof-eligible result atom
\newcommand*\codep@currentproofid{}    % current proof atom ID or empty
% Proof-nesting save stack (for nested proofs):
% Each entry: {currentproofid, proofdisplaypending, proofbind-marker}
\newtoks\codep@proofneststack           % token register used as a stack

% Per-proof deferred proofbind marker (for cmd/endproof serialization):
% When \codepproofof writes a proofbind, this stores {label, mode}.
% When bindproofparent succeeds, this is cleared.
% At cmd/endproof/before, if non-empty, serialize as \codep@proofbind.
\newcommand*\codep@pendingproofbind{}   % empty = no deferred bind; else {label}{mode}
```

**Equation-local accumulator state** (added by the equation-fix revision):

```tex
\newcommand*\codep@currenteqsourceid{}   % tentative equation source atom aN
\newcommand*\codep@eqfallbacksourceid{}  % enclosing source atom for outer/off mode
% plus: pending ref list, Track 2 start counter, numbered-block flag
```

**What is removed:** `\codep@currentatom`, `\codep@currenttype`, `\codep@sourceatom`, `\codep@nestlevel`, `\codep@trackedlevel`, `\codep@lasttheorematom`, `\ifcodep@intheorem`, `\ifcodep@proofdeferred`, `\codep@restate@depth`, `\codep@pushcurrentatom`, `\codep@popcurrentatom`.

### 2.3 Core Macros

```tex
\def\codep@allocatomid#1#2{...}      % #1 <- id macro (e.g. \codep@thisatomid),
                                      % #2 = kind string
\def\codep@alloctargetid#1#2{...}    % #1 <- id macro, #2 = kind string

\def\codep@ctxpush#1#2{...}          % GLOBAL push: #1=atom-id, #2=kind
\def\codep@ctxpop#1{...}             % GLOBAL pop: #1=expected kind
                                      % MUST hard-error on mismatch/underflow
\def\codep@ctxpeekid#1{...}          % #1 <- top atom ID or \@empty
\def\codep@ctxpeekkind#1{...}        % #1 <- top kind or \@empty

\def\codep@closeparagraphifopen{...} % idempotent: full paragraph finalization

\def\codep@recordlabelowner#1{...}   % #1 = label key -> see equation label buffering model below
\def\codep@writerefevent#1{...}      % #1 = target label key

<!-- Fixed: MINOR 20 — removed \codep@bindprooflabel (not used; \codep@proofbind is the aux record) -->
\def\codep@bindproofparent#1#2#3{...}% #1=proof-atom-id, #2=parent-atom-id, #3=mode
```

<!-- Fixed: R4/R8/R10 — bindproofparent binds in memory; serialization deferred to proof end -->
<!-- Fixed: R8-MAJOR — defer proof-parent serialization to proof end to allow codepproofof override -->
`\codep@bindproofparent` is the single authoritative proof-resolution macro. It MUST:
1. Store the binding **in memory only** (proof-parent table: `proof-id -> {parent-id, mode}`)
2. Emit `\codep@meta{#1}{display}{<parent-display>*}` (looked up from parent's metadata)
3. Emit anchor metadata: for `statement` mode, `\codep@meta{#1}{anchor}{<parent-anchor>}`. For `proof` mode, the caller (`\codepproofof*`) handles anchor separately since it must place a hypertarget at the call site. If hyperref not loaded, emit `\codep@meta{#1}{anchor}{}`.

**It does NOT write `\codep@proofparent` to `.aux` or `.cdp` at call time.** Serialization is deferred to `cmd/endproof/before` (see below). This allows a later `\codepproofof` to override a replay-loaded or adjacent binding before anything hits disk.

Every resolved proof path (replay-loaded, adjacent, `\codepproofof`, re-check) calls this macro. The single serialization point is `cmd/endproof/before`.

`\codep@ctxpop` must include a hard mismatch/underflow check. `\codep@ctxpeekkind` is required for mode decisions and assertions -- `ctxpeekid` alone is too weak.

<!-- Fixed: BLOCKER 3 -->
<!-- Fixed: R13b-MAJOR 5 — closeparagraphifopen render flush is deferred snapshot, not immediate typesetting -->
**`\codep@closeparagraphifopen` is full paragraph finalization, not a simple pop.** When `\ifcodep@paragraphopen` is true, it must:
1. Snapshot the current paragraph's rendering state (deferred backref data).
2. Call the render flush hook so that any pending paragraph display is emitted.
3. `\codep@ctxpop{paragraph}` -- pop the paragraph from the context stack.
4. `\codep@paragraphopenfalse` -- clear the paragraph-open flag.

**Render safety note:** Step 2 uses the **same deferred snapshot mechanism** as `para/end`. It does NOT force immediate typesetting of backrefs into the document stream. Instead, it snapshots the current backref state for later rendering by the deferred render pipeline in `codependent-render.sty`. This is safe to call at any hook site (including `cmd/theorem/before` and `cmd/proof/before`) because no TeX box-building or node insertion occurs at flush time — only state capture. The actual rendering tokens are emitted later, at the point where the render hook fires during normal document processing (see `\codep@render@para@emitdeferred` in `codependent-render.sty` lines ~358ff). This matches the current package's deferred render pipeline.

After `\codep@closeparagraphifopen` runs, the subsequent `para/end` hook (which will fire later in the normal TeX event sequence) must be a no-op: `para/end` checks `\ifcodep@paragraphopen` and only acts when it is true. Since `closeparagraphifopen` already cleared the flag, `para/end` skips its body. This makes the pair idempotent.

This design is required because `cmd/theorem/before` and `cmd/proof/before` fire BEFORE the prior `para/end` in LaTeX's hook ordering. Without full finalization in `closeparagraphifopen`, the paragraph rendering state would be lost or the later `para/end` would underflow the context stack.

<!-- Fixed: BLOCKER 10 — owner/anchor/source are determined at env/Q/after time, not at \label time; may be fallback-or-empty in outer/off mode -->
<!-- Fixed: R13b-BLOCKER 4 — buffer stores equation-counter and anchor snapshots captured at \label time -->
**Equation label buffering model.** `\codep@recordlabelowner` is called at `\label` time inside an equation environment. Owner and source atom are NOT known at `\label` time; they are determined at `env/Q/after`. However, the per-row display tag and hyperref anchor ARE available at `\label` time (amsmath sets `\theequation` and `\@currentHref` before firing the `\label` hook). These must be captured immediately because they will change for subsequent rows in a multi-row environment. The full buffered data model is:

1. **At `\label{eq:foo}` time** (inside equation body):
   - Allocate a fresh target ID `qK` via `\codep@alloctargetid`
   - Write `\codep@labelentity{eq:foo}{qK}` to `.aux` immediately (label-to-entity binding is unconditional)
   - Capture `\codep@tmp@eqcountersnap` = current value of `\theequation` (the equation counter display string for this row, e.g., `1` or `4.3`)
   - Capture `\codep@tmp@eqanchorsnap` = `\@currentHref` if hyperref is loaded, else `\@empty`
   - Append `{qK, eq:foo, \jobname.tex:\the\inputlineno:1, \codep@tmp@eqcountersnap, \codep@tmp@eqanchorsnap}` to the equation label buffer (a token list local to this equation block)
   - The owner atom ID is NOT known yet (it depends on `equations` mode and enclosing context, which are resolved at `env/Q/after`)

   **Why capture at `\label` time:** In a multi-row `align`, each row has its own `\theequation` and `\@currentHref` values. By the time `env/Q/after` fires, both reflect only the last row. The per-row snapshot approach is the only way to recover correct `display` and `anchor` values for each row independently.

2. **At `env/Q/after`** (after amsmath has finalized all tags and labels):
   - Determine the owner atom ID for this block:
     - In `equations=all` or top-level `equations=outer`: use the equation source atom `aN` (the atom allocated at `env/Q/begin` for this block)
     - In `equations=outer` (nested) or `equations=off`: use the fallback enclosing atom ID if one is on the context stack, else use the empty string
   - If the block produced at least one number:
     - For each buffered label entry `{qK, label-key, src, eqcountersnap, eqanchorsnap}`:
       - Write `\codep@targetdecl{qK}{equation}`
       - Write `\codep@meta{qK}{display}{(\codep@tmp@eqcountersnap)}` — formatted display using the per-row counter snapshot
       - Write `\codep@meta{qK}{anchor}{\codep@tmp@eqanchorsnap}` if non-empty, else `\codep@meta{qK}{anchor}{}`
       - Write `\codep@meta{qK}{owner}{<owner-atom-id-or-empty>}` (may be empty in outer/off with no enclosing source)
       - Write `\codep@meta{qK}{src}{<captured-src>}`
   - If the block produced no number:
     - The buffered label entries are discarded (the `labelentity` records already written are harmless -- they point to `qK` IDs that have no `targetdecl`, so they will not resolve during replay)

### 2.4 Hook Plan (theorem, proof, paragraph, equation)

<!-- Fixed: R14-BLOCKER — three-point timing: aux at load, label at before, ref at end -->
Three distinct hook timing points:

1. **Aux record readers**: defined at **package load time** (active when `.aux` is read during `\begin{document}`).
2. **Label wrapper** (`\codep@recordlabelowner`): installed at **`begindocument/before`**. This MUST run before amsmath's `begindocument/end` hook which snapshots `\label` into `\ltx@label` for use inside display math (`amsmath.sty` line 1228). If the label wrapper installs later, amsmath's snapshot bypasses it and equation labels are silently untracked. This matches the current .sty's timing.
3. **Ref interception patches**: installed at **`begindocument/end`**. This fires AFTER hyperref/cleveref finalize their `\ref`/`\cref` wrappers in `\AtBeginDocument`. Queue flushes (proof-bind, ref-event) also happen here.

#### Tracked theorem-like envs `E`

**`cmd/E/before`:**
- `\codep@closeparagraphifopen`
- If replay branch: increment `replaydepth` and `suppressdepth`, no atom allocation
- Else if nested tracked env: increment `trackeddepth` and `suppressdepth`, no new atom
- Else (outermost non-replay):
  - Allocate `aN` via `\codep@allocatomid`
  - `\codep@ctxpush{aN}{E}`
  - Write `\codep@atomdecl{aN}{E}`, `\codep@meta{aN}{env}{E}`, `\codep@meta{aN}{src}{...}`

<!-- Fixed: NEW MAJOR — no-hyperref else branch added to theorem emit site -->
**`cmd/E/after`** (theorem counter is now stepped):
- Write `\codep@meta{aN}{display}{\theE}` (or `\theatom`)
- If hyperref loaded: write `\codep@meta{aN}{anchor}{\@currentHref}`
- Else: write `\codep@meta{aN}{anchor}{}`

<!-- Fixed: R13b-BLOCKER 5 — starred tracked environments specified -->
**Starred variants (`theorem*`, `definition*`, etc.):** Starred tracked environments are tracked **identically** to their unstarred counterparts. They:
- Allocate atoms via `\codep@allocatomid` (same as unstarred)
- Push context via `\codep@ctxpush{aN}{E}` (same)
- Write all records (`atomdecl`, `meta`, `labelentity`, `refevent`) (same)
- Use `\theatom` for display (see below)

The key difference is that the theorem backend suppresses the theorem counter step for starred variants (since they have no number from the theorem system). **Codependent does NOT rely on the theorem counter step.** Instead, `\codep@allocatomid` steps the shared `\c@atom` counter directly (via `\global\advance\codep@atomid by 1`), and `\theatom` is always valid. The display string `\theatom` is the atom sequence number, not a section-prefixed theorem number. For starred envs in `equations=all` mode, this is the expected and correct behavior.

This is the current `.sty` behavior: `\codep@hooktheorem@begin` hooks into both starred and unstarred variants via `\codep@hooktheorem` (which calls `\AddToHook{cmd/#1/before}` and `\AddToHook{cmd/end#1/before}` for the given env name), and the begin hook allocates atoms unconditionally for outermost non-replay occurrences regardless of whether the variant is starred. No special-casing of starred envs is needed in the new architecture.

**`cmd/endE/before`:**
- Pop or decrement nested depth
- If outermost non-replay: set `\codep@pendingresultid` to `aN`

<!-- Fixed: R13b-MINOR — rewritten to state the normative rule first, then note current .sty behavior parenthetically -->
**Proof-eligible environments.** ALL tracked theorem-like environments are proof-eligible. `\codep@pendingresultid` is set unconditionally at the end of any outermost tracked env, without distinguishing "result" from "non-result" environments. A proof immediately after any tracked env (theorem, definition, lemma, remark, etc.) inherits adjacency. *[Continuity note: this matches the current `.sty` behavior and is preserved in the redesign.]*

`\codep@pendingresultid` is set unconditionally at the end of any outermost tracked env. It is cleared by:
- A paragraph beginning at top level (intervening text breaks adjacency)
- A sectioning command (`cmd/section/before` etc.)
- Another tracked env beginning (the new env replaces the pending result)
- An equation env beginning (`env/Q/begin`)

A future `results={theorem,lemma,...}` / `nonresults={definition,...}` option could refine eligibility, but for the graph redesign all tracked envs are eligible. The test `test-proofs-after-non-result.lvt` should expect adjacency inheritance for all tracked env types.

**`env/E/after`:** Rendering flush only; no semantic state changes.

#### Proofs
<!-- Fixed: BLOCKER 4 -->

**Complete proof state machine.** The proof lifecycle manages two pieces of mutable state:
- `\codep@currentproofid` -- the atom ID of the currently open proof (or empty outside proofs)
- `\ifcodep@proofdisplaypending` -- true when the proof's display/anchor metadata has not yet been assigned

State transitions are specified exhaustively below.

<!-- Fixed: R12 — nested proof state saved/restored; nested check before push -->
<!-- Fixed: R13b-BLOCKER 2 — proofs=off branch specified -->
**`cmd/proof/before`:**
0. **If `proofs=off`:** increment `suppressdepth` only. Do NOT allocate a proof atom, do NOT push context, do NOT check adjacency, do NOT write any records. Skip all remaining steps in this hook. The corresponding `cmd/endproof/before` must mirror this: if `proofs=off`, decrement `suppressdepth` only and skip all other serialization steps. This matches the current `.sty` guard `\ifbool{codep@proofsnumbered}{...}{\advance\codep@nestlevel by 1}` (see `\codep@hookproof@begin` / `\ifbool{codep@proofsnumbered}` at line ~665). The `proofs` option value is hashed into the config hash (§2.12), so changing `proofs=on` to `proofs=off` between runs triggers a stale-aux warning and fresh record rewrite.
1. `\codep@closeparagraphifopen`
2. **Save outer proof state** if `\codep@currentproofid` is non-empty (nested proof):
   - Push `{currentproofid, proofdisplaypending, pending-proofbind-marker}` onto a proof-nesting save stack
   - Set `\codep@isnested` flag for use in step 8
3. Allocate proof atom `aN` via `\codep@allocatomid`
4. **Set** `\gdef\codep@currentproofid{aN}`
5. `\codep@ctxpush{aN}{proof}`
6. Write `\codep@atomdecl{aN}{proof}` and `\codep@meta{aN}{src}{\jobname.tex:\the\inputlineno:1}`
7. **Set** `\codep@proofdisplaypendingtrue`
8. Check the replay-loaded proof-parent table for this exact proof ID:
   - If a resolved parent for `aN` is already present in memory:
     - `\codep@bindproofparent{aN}{<parent-atom-id>}{<mode>}` (binds in memory + emits display/anchor metadata; .aux/.cdp deferred to proof end)
     - **Clear** `\codep@proofdisplaypendingfalse`
     - **Clear** `\gdef\codep@pendingresultid{}`
     - Skip adjacency and standalone fallback for this proof
9. Otherwise, check adjacent binding (only if NOT nested):
   - If `\codep@isnested`: **Do NOT consume `\codep@pendingresultid`.** Nested proofs are never auto-adjacent.
   - Else if `\codep@pendingresultid` is non-empty:
     - `\codep@bindproofparent{aN}{<pendingresultid>}{statement}` (binds in memory + emits display/anchor metadata; .aux/.cdp deferred to proof end)
     - **Clear** `\codep@proofdisplaypendingfalse`
     - **Clear** `\gdef\codep@pendingresultid{}`
<!-- Fixed: R13b-MINOR — renumbered to avoid duplicate step 9 -->
10. Otherwise, leave `\ifcodep@proofdisplaypending` true. The proof will be resolved later by `\codepproofof`, by the first-proof-paragraph re-check, or by the proof-end re-check before standalone fallback.

<!-- Fixed: R2-BLOCKER 4; superseded by authoritative \codepproofof spec in §2.10 -->
**`\codepproofof{label}` / `\codepproofof*{label}`:** See §2.10 for the authoritative specification. Key point: this macro runs **unconditionally** (not gated on pending) and can override a preloaded parent.

<!-- Fixed: R2-NEW-MAJOR (standalone proof anchor creation) -->
**Standalone proof fallback materialization:** When a proof is still pending at the fallback point (the first `para/begin` inside the proof, or `cmd/endproof/before` for an empty proof), materialize standalone proof metadata at that site:
- Step the proof display counter (`\refstepcounter{atom}`) so the standalone proof has a stable `N`
- Emit `\codep@meta{aN}{display}{\theatom*}`
- If `hyperref` is loaded, create a dedicated hypertarget `codep.proof.aN` at the fallback site and emit `\codep@meta{aN}{anchor}{codep.proof.aN}`
- If `hyperref` is not loaded, emit `\codep@meta{aN}{anchor}{}`
- Clear `\codep@proofdisplaypendingfalse`
- Issue the standalone-proof warning if `proofwarnings` is enabled

The same standalone-fallback helper is called from both fallback sites so empty proofs and non-empty proofs create the same anchor form.

<!-- Fixed: BLOCKER 6 — para/begin and endproof must re-check resolved-parent table before calling standalone helper -->
**`para/begin` inside proof (first paragraph, while display is pending):**
- If `\ifcodep@proofdisplaypending` is true:
  1. Re-check the resolved proof-parent table for the current proof ID (`\codep@currentproofid`):
     - If a resolved parent is now present (loaded from aux replay during this paragraph event or earlier):
       - `\codep@bindproofparent{aN}{<parent-atom-id>}{<mode>}` (binds in memory + emits display/anchor metadata; .aux/.cdp deferred to proof end)
       - **Clear** `\codep@proofdisplaypendingfalse`
     - Else (still unresolved): call the standalone proof fallback materialization helper (see above)

**`cmd/endproof/before`:**
1. If `\ifcodep@proofdisplaypending` is true (empty proof body, or proof still pending after `\codepproofof`):
   - Re-check the resolved proof-parent table for the current proof ID:
     - If a resolved parent is now present:
       - `\codep@bindproofparent{aN}{<parent-atom-id>}{<mode>}` (binds in memory + emits display/anchor metadata; .aux/.cdp deferred to proof end)
       - **Clear** `\codep@proofdisplaypendingfalse`
     - Else: call the standalone proof fallback materialization helper (see above)
2. **Serialize proof parentage to `.aux` and `.cdp`:** Look up `\codep@currentproofid` in the in-memory proof-parent table.
   - If a binding exists: write `\codep@proofparent{aN}{<parent-id>}{<mode>}` to `.aux` and `\codep@cdp@proofparent{aN}{<parent-id>}{<mode>}` to `.cdp`
   - If no binding (standalone proof): do NOT write `proofparent` (standalone proofs have no parent record)
   - If an unresolved `proofbind` was requested by `\codepproofof`: write `\codep@proofbind{aN}{<label>}{<mode>}` to `.aux` and `\codep@cdp@proofbind{aN}{<label>}{<mode>}` to `.cdp`
   - This is the **single serialization point** for proof parentage. No earlier hook writes these records.
3. `\codep@ctxpop{proof}`
4. **Clear `\codep@pendingresultid`** — a theorem/lemma created inside this proof must not leak its pending state and auto-bind a later top-level proof.
5. **Restore outer proof state:** If the proof-nesting save stack is non-empty, pop `{currentproofid, proofdisplaypending, pending-proofbind-marker}` and restore them. Otherwise, clear `\gdef\codep@currentproofid{}`.
6. Rendering: flush inline/orphan display

**`env/proof/after`:** Rendering flush only; no semantic state changes.

#### Paragraphs

<!-- Fixed: R13 — para/begin clears pendingresultid (intervening text breaks adjacency) -->
<!-- Fixed: R13b-BLOCKER 1 — paragraphs=off branch specified -->
**`para/begin`:**
- Emit deferred previous-paragraph rendering
- **Clear `\codep@pendingresultid`** (a top-level paragraph breaks proof adjacency)
- If inside proof with pending display: re-check resolved proof-parent table first; if resolved, apply binding and clear pending; else call standalone proof fallback materialization helper (§2.4 Proofs)
<!-- Fixed: R14-MAJOR — paragraphs=off must not touch suppressdepth (unbalanced) -->
- **If `paragraphs=off`:** skip paragraph atom allocation entirely. Do NOT increment `suppressdepth` (that would be unbalanced since `para/end` doesn't decrement). Do NOT push context, do NOT set `\ifcodep@paragraphopen`, do NOT write any records. The `para/end` hook checks `\ifcodep@paragraphopen`; since it was never set, `para/end` is a no-op. Paragraph suppression for content inside other atoms (theorems, proofs) is already handled by their own `suppressdepth` increments — `paragraphs=off` only affects top-level bare paragraphs.
- If `suppressdepth > 0` or `ctxdepth > 0`: do not open paragraph atom
- Else:
  - Allocate paragraph atom `aN`
  - `\codep@ctxpush{aN}{paragraph}`
  - `\codep@paragraphopentrue`
  - `\refstepcounter{atom}`
  - Write `atomdecl`, `display`, `anchor`, `src`

**`para/end`:**
- If paragraph open:
  - Snapshot paragraph rendering
  - `\codep@ctxpop{paragraph}`
  - `\codep@paragraphopenfalse`

#### Equations

Tracked equation environments: `equation`, `align`, `gather`, `multline`, `flalign`.

<!-- Fixed: R13b-MAJOR 4 — custom equation env registration specified -->
**User-registered equation environments.** `\codeptrackeq{myenv}` and `\codeptrackalign{myenv}` install the same hooks as the built-in tracked equation environments listed above. User-registered environments participate in the buffer/owner model identically:

- `\codeptrackeq{myenv}` installs the `env/Q/begin`, `env/Q/after` hook pair for a single-row-style environment (`equation`-like: at most one label per env).
- `\codeptrackalign{myenv}` installs the same pair for a multi-row-style environment (`align`-like: multiple `\label` calls, one `qK` target per row).
- Both registration macros also call `\codep@suppressenv{myenv*}` for the starred (unnumbered) variant if it exists.
- The registered environment names are included in the config hash (§2.12). Adding or removing a registered environment between runs triggers a stale-aux warning and full rewrite.

The sentence "Tracked equation environments: `equation`, `align`, ...`" above is the default set installed by `\codep@installequations`. User-registered envs extend that set dynamically.

<!-- Fixed: R2-BLOCKER 10 -->
**`env/Q/begin`:**
- `\codep@closeparagraphifopen`
- Clear `\codep@pendingresultid`
- Increment `\codep@suppressdepth`
- Capture the current enclosing source atom into `\codep@eqfallbacksourceid` via `\codep@ctxpeekid`
- Clear `\codep@currenteqsourceid`
- Open the equation accumulator
- If mode says the equation block owns refs (`equations=all`, or `equations=outer` with no enclosing source atom):
  - Allocate source atom `aN`, store it in `\codep@currenteqsourceid`
  - `\codep@ctxpush{aN}{equation}`
  - Create the dedicated block anchor if `hyperref` is loaded; otherwise plan to emit an empty anchor value
- If mode says the block does NOT own refs (`equations=outer` with an enclosing source atom, or `equations=off`):
  - Do not allocate an equation source atom
  - Keep `\codep@eqfallbacksourceid` as the only possible source for buffered ref replay

**During body:**
- `\codep@recordlabelowner{eq:...}` always allocates a distinct `qK` target and appends it to the equation-label buffer
- All equation ref events are buffered until `env/Q/after`; no equation ref event is emitted immediately

**`env/Q/after`** (NOT `env/Q/end` -- amsmath may fire label/tag work between `end` and `after`):
- If the block produced at least one number:
  - If `\codep@currenteqsourceid` is non-empty, emit the equation-source atom records (`atomdecl`, `display`, `anchor`, `src`) for that `aN`
  - For each buffered label entry `{qK, label-key, src}`:
    - Emit `\codep@targetdecl{qK}{equation}`
    - Emit `\codep@meta{qK}{display}{<row-tag>}`
    - Emit `\codep@meta{qK}{anchor}{<row-anchor>}` if `hyperref` is loaded, else `\codep@meta{qK}{anchor}{}`
    - Emit `\codep@meta{qK}{owner}{\codep@currenteqsourceid}` when a source atom exists
    - Otherwise emit `\codep@meta{qK}{owner}{\codep@eqfallbacksourceid}` if the fallback source is non-empty, else `\codep@meta{qK}{owner}{}`
    - Emit `\codep@meta{qK}{src}{<captured-src>}`
  - Flush buffered refs from `\codep@currenteqsourceid` when it exists
  - Otherwise flush buffered refs from `\codep@eqfallbacksourceid` when it exists
  - Otherwise drop the buffered refs
- If the block produced no number:
  - Discard any tentative equation source atom. **The discarded `aN` ID leaves a hole in the sequence and is NEVER reused.** The monotone counter `\codep@atomid` only advances; it is never decremented. This means an all-`\notag` align block wastes one atom ID -- that is acceptable. The alternative (deferring allocation until numbering is known) would require restructuring the context stack mid-equation, which is more fragile.
  - Discard buffered q-target materialization for this block (the already-written `labelentity` records are harmless)
  - Replay buffered refs from `\codep@eqfallbacksourceid` if it is non-empty; otherwise drop them
- `\codep@ctxpop{equation}` only if `\codep@currenteqsourceid` was pushed
- Decrement `\codep@suppressdepth`
- Render the equation block

**Mode interaction summary:**

| `equations=` | Inside theorem/proof? | Equation opens source atom? | Refs attributed to |
|---|---|---|---|
| `all` | yes | yes | equation atom `aN` |
| `all` | no | yes | equation atom `aN` |
| `outer` | yes | no | enclosing theorem/proof atom |
| `outer` | no | yes | equation atom `aN` |
| `off` | either | no | enclosing atom (or dropped) |

**Track 2 display:** One source atom per numbered display block (not per numbered line). Display is metadata only, typically `(1--3)` or `(1)`. Attribution is coarser: if only one row uses `\ref`, the backref still names the block. If sparse `\notag` layouts later need exact displays like `(1,3)`, add member-span metadata; do not switch the identity model.

#### Sectioning and source-breaking commands
<!-- Fixed: BLOCKER 1 -->

`cmd/section/before`, `cmd/subsection/before`, `cmd/subsubsection/before`, `cmd/chapter/before`, `cmd/paragraph/before`, `cmd/subparagraph/before`:
- `\codep@closeparagraphifopen`
- Clear `\codep@pendingresultid`
- Set one-shot sectioning suppression flag: `\global\booltrue{codep@sectioning}`

The `codep@sectioning` flag is a one-shot boolean (not `suppressdepth`). It fires in `para/begin` before the paragraph allocation check: if `codep@sectioning` is true, clear it (`\global\boolfalse{codep@sectioning}`) and skip paragraph atom allocation for this one paragraph. The flag is consumed exactly once per sectioning command, so nested section headings each get their own flag-set/flag-clear cycle. *[Continuity note: this is the same mechanism as in the current `.sty`.]*

Any tracked env begin also clears `\codep@pendingresultid` unless consumed by an immediately adjacent proof.

#### Environment and command suppression
<!-- Fixed: BLOCKER 2 -->

The suppression infrastructure increments/decrements `\codep@suppressdepth` around environments and commands whose body content must not produce paragraph atoms. This infrastructure survives all waves unchanged --- it is orthogonal to the graph redesign.

**`\codep@suppressenv{envname}`:** Installs `\AtBeginEnvironment{envname}{\advance\codep@suppressdepth by 1}` and `\AtEndEnvironment{envname}{\advance\codep@suppressdepth by -1}`.

**Standard suppressed environments** (installed by `\codep@installsuppress`):
- List environments: `enumerate`, `itemize`, `description`
- Block environments: `quote`, `quotation`, `figure`, `table`, `minipage`, `tabular`, `tabularx`, `longtable`, `trivlist`
- Unnumbered display math: `equation*`, `displaymath`, `align*`, `gather*`, `multline*`, `flalign*`

Note: numbered display math environments (`equation`, `align`, `gather`, `multline`, `flalign`) use `\codep@trackeqenv` / `\codep@trackalignenv` instead of `\codep@suppressenv`, which provides both suppression and equation tracking.

**`\codep@suppresscmd{command}`:** Patches `command` with `\pretocmd` / `\apptocmd` to increment `suppressdepth` before the body and decrement after.

**Standard suppressed commands** (installed by `\codep@suppresscommands`):
- `\footnote`, `\parbox`, `\maketitle`

Note: `\caption` is NOT patched because its complex calling convention (`\@ifstar` + optional arg) makes etoolbox patching unreliable; captions appear only inside `figure`/`table` environments, which are already suppressed at the env level.

**Conditional package suppression** (installed at `begindocument/end`):
- `tcolorbox` (if loaded): `\codep@suppressenv{tcolorbox}`
- `mdframed` (if loaded): `\codep@suppressenv{mdframed}`
- `enumitem` (if loaded): patches `\newlist` so every user-defined list environment is automatically registered for suppression

**Suppression guard in `para/begin`:** The paragraph allocation check tests `suppressdepth > 0` (in the new architecture) or `nestlevel > 0` (current architecture). When true, `para/begin` skips paragraph atom allocation entirely. This is the single guard point --- suppression works by ensuring `suppressdepth > 0` whenever content should not produce paragraph atoms.

<!-- Fixed: MAJOR 13 -->
#### Hook ordering and `\DeclareHookRule` requirements

<!-- Fixed: R14 — three-point timing matching §2.4 header -->
Three distinct hook timing points (matching §2.4 header):

1. **Aux record readers**: defined at **package load time** (active during `.aux` read).

2. **Label wrapper** (`\codep@recordlabelowner`): installed at **`begindocument/before`**. Must run before amsmath's `begindocument/end` snapshot of `\label` into `\ltx@label`. Cleveref compatibility: codependent's label wrapper saves `\label` at `begindocument/before`; cleveref installs its optional-argument wrapper in `\AtBeginDocument`; amsmath snapshots the result at `begindocument/end`. All three compose correctly because each wraps the previous.

3. **Ref interception patches**: installed at **`begindocument/end`**. Fires AFTER hyperref/cleveref finalize `\ref`/`\cref` wrappers. Queue flushes also happen here.

Required ordering rules:

1. **Ref interception after hyperref/cleveref wrapping:** `\codep@writerefevent` wrapper around `\@setref` installs at `begindocument/end`.

2. **Label wrapper before amsmath snapshot:** `\codep@recordlabelowner` patches `\label` at `begindocument/before`. Amsmath snapshots `\label` into `\ltx@label` at `begindocument/end` — the snapshot captures the already-wrapped `\label`.

3. **Sectioning hooks:** `\AddToHook{cmd/<level>/before}[codependent/sectioning]{...}` uses the named label `codependent/sectioning`. No explicit `\DeclareHookRule` is needed for sectioning because the one-shot flag mechanism is order-independent with respect to other packages' sectioning hooks.

4. **Paragraph hooks:** `\AddToHook{para/begin}` and `\AddToHook{para/end}` use default ordering. No other package is known to install semantic `para/begin` hooks that would conflict.

The redesign uses `\AddToHook{begindocument/end}[codependent]{...}` for ref/label patches (after hyperref/cleveref finalize) and defines aux record handlers at package load time (so they're active during `.aux` read). This two-point installation must be preserved through all waves.

<!-- Fixed: R13b-MAJOR 1 — begin-document refs coverage: two-phase install or explicit gap documentation -->
**Coverage of refs/labels in `\AtBeginDocument` hooks.** Moving ref/label wrapping to `begindocument/end` means that any `\ref` or `\label` call executed from user or package `\AtBeginDocument` hooks fires BEFORE codependent's wrappers are installed and is therefore NOT tracked. There are two acceptable approaches:

- **Two-phase install (recommended):** Install a PRELIMINARY wrapper at `begindocument/before` that captures the current `\ref`/`\label` definitions and replaces them with simple codependent-tracking stubs. At `begindocument/end`, UPGRADE those stubs to the full pipeline (wrapping the now-finalized hyperref/cleveref definitions). The preliminary wrapper is minimal — it just records `(context, target-label)` into a queue; the final wrapper is the complete ref pipeline. This preserves tracking for refs/labels from `\AtBeginDocument` hooks while still wrapping the final hyperref/cleveref definitions.

- **Explicit gap documentation (acceptable):** Document that refs/labels issued inside `\AtBeginDocument` hooks are not tracked. This gap is acceptable because: (a) such refs are uncommon in mathematical documents; (b) the current `.sty` already installs at `begindocument/before` which gives it priority over hyperref/cleveref's `\AtBeginDocument` patches but does not wrap them (see `codependent.sty` lines 1789 and 1975 — the current install point). The new `begindocument/end` install eliminates a known wrapping-order fragility at the cost of this gap.

The choice between these approaches is deferred to Wave 2 implementation. If the two-phase install is used, the preliminary stubs and final upgrade must both be tested. If the gap approach is used, add a test `test-label-in-atbegindocument.lvt` that verifies the gap is benign (i.e., the document compiles without error; the ref just goes untracked).

### 2.5 Reference Interception

Source ownership is read only from the explicit global stack top. There is no shared slot updated sometimes with `\gdef` and sometimes with local `\def`.

Write-time dedup: `(source-atom-id, target-label)` -- suppress duplicate writes from `\@setref` plus `\cref@getlabel` plus hyperref wrappers.

Replay-time dedup: `(source-atom-id, target-entity-id)` -- collapse multiple labels on the same theorem atom but keep distinct equation labels distinct.

<!-- Fixed: R13b-MAJOR 2 — \ifmeasuring@ guard specified normatively -->
**amsmath measuring-pass guard.** All ref interception (`\codep@writerefevent`) must include a guard against amsmath's double-pass measurement. When `amsmath` is loaded, `align`-like environments are processed **twice**: once in a measuring pass (to compute column widths) and once for typesetting. Without a guard, each `\ref` inside an `align` body fires twice, producing duplicate `refevent` records and duplicate backref edges. The mandatory guard pattern is:

```tex
\@ifundefined{ifmeasuring@}{%
  \codep@writerefevent{#1}%
}{%
  \ifmeasuring@\else
    \codep@writerefevent{#1}%
  \fi
}
```

This tests whether `\ifmeasuring@` is defined (it is defined by amsmath at load time) and, if so, suppresses the ref event during the measuring pass. This guard applies to the `\@setref` wrapper, the `\cref@getlabel` wrapper, and any other ref-interception hook that calls `\codep@writerefevent`. The current `.sty` implements this guard in `\codep@writeatomref` at lines ~1352--1357. The guard must be preserved through all waves.

Storage backend may stay the current csname linked list, keyed by resolved entity ID:
```tex
\codep@brcount@<entity-id>
\codep@brnode@<entity-id>@<k> = <source-atom-id>
```

<!-- Fixed: R13b-BLOCKER 3 — non-equation label binding path specified -->
#### Non-equation label binding

When `\label{key}` is called **outside an equation environment** (i.e., inside the body of a tracked theorem-like env, inside a proof, or inside a paragraph atom), the label wrapper must emit:

```tex
\codep@labelentity{key}{aN}
```

where `aN` is the atom ID obtained from `\codep@ctxpeekid` at the moment `\label` fires. This is the **generic label-binding path**. It binds the label text `key` to the currently open source atom so that future `\ref{key}` calls resolve to that atom via the `labelentity` table.

This path is distinct from the **equation-specific label-binding path** (§2.4 Equations), which allocates a fresh `qK` target and defers all metadata until `env/Q/after`. The label wrapper must check whether it is currently inside an equation accumulator (`\codep@suppressdepth > 0` AND an equation body is active) and dispatch to the equation path in that case; otherwise it uses this generic path.

**If `\codep@ctxpeekid` returns empty** (the label fires outside any tracked atom, e.g., in a suppressed environment or before tracking begins), the `labelentity` record is NOT emitted. The label is processed normally by the underlying LaTeX/hyperref/cleveref machinery, but codependent records no ownership. This matches the current `.sty` where `\codep@writelbltype` checks `\codep@currentatom` is non-empty before writing (see lines ~2010--2030 in `codependent.sty`).

**Replay semantics:** The `\codep@labelentity{key}{aN}` record, when replayed from `.aux`, populates the `label -> entity-id` table. During `begindocument/end` queue flush, `refevent{aN}{key}` records look up `key` in this table to resolve the target entity for graph-edge construction.

### 2.6 .aux Protocol

#### Header

```tex
\codep@auxheader{3}{<graph-config-hash>}
```

The config hash covers every option that changes allocation or display metadata: tracked env sets, `paragraphs`, `proofs`, `equations`, registered equation envs, and numbering depth. On header mismatch or missing header: suppress package backref rendering for that run, write fresh records, issue a rerun warning.

#### Record definitions
<!-- Fixed: BLOCKER 11 -->

```tex
\providecommand*\codep@atomdecl[2]{}     % {atom-id}{kind}
\providecommand*\codep@targetdecl[2]{}   % {target-id}{kind}
\providecommand*\codep@meta[3]{}         % {entity-id}{key}{value}
\providecommand*\codep@labelentity[2]{}  % {label}{entity-id}
\providecommand*\codep@refevent[2]{}     % {source-atom-id}{target-label}
\providecommand*\codep@proofparent[3]{}  % {proof-atom-id}{parent-atom-id}{mode}
\providecommand*\codep@proofbind[3]{}    % {proof-atom-id}{label}{mode}
```

**Authoritative schema per entity type:**

| Record | Arguments | Used by | Loaded at aux-read? |
|--------|-----------|---------|---------------------|
| `atomdecl` | `{atom-id}{kind}` | atoms (theorem, proof, paragraph, equation) | Yes, immediate |
| `targetdecl` | `{target-id}{kind}` | targets (equation labels) | Yes, immediate |
| `meta` | `{entity-id}{key}{value}` | both atoms and targets | Yes, immediate |
| `labelentity` | `{label}{entity-id}` | both (maps LaTeX label to entity ID) | Yes, immediate |
| `refevent` | `{source-atom-id}{target-label}` | edges (source atom references target) | Queued, flushed at `begindocument/end` |
| `proofparent` | `{proof-atom-id}{parent-atom-id}{mode}` | proof atoms only (resolved binding) | Yes, immediate |
| `proofbind` | `{proof-atom-id}{label}{mode}` | proof atoms only (unresolved binding) | Queued, flushed at `begindocument/end` |

<!-- Fixed: R9 — duplicate meta writes are legal, last-write-wins -->
**`\codep@meta` override semantics:** Multiple `\codep@meta` records with the same `{entity-id}{key}` may appear in a single run. **Last write wins** — the reader overwrites previous values for the same key. This is required because proof binding may emit `display`/`anchor` metadata at bind time (from `bindproofparent`), then re-emit different values if the binding is invalidated and standalone fallback fires. The same holds for `\codepproofof*` overriding a statement-mode anchor with a proof-mode anchor.

<!-- Fixed: R2-BLOCKER 11 -->
**Metadata keys by entity type:**

| Key | Atoms (theorem/proof/paragraph/equation) | Targets (q-labels) | Description |
|-----|------------------------------------------|---------------------|-------------|
| `display` | Required | Required | Human-readable display string (`1.2`, `(1)`, etc.) |
| `anchor` | Optional | Optional | Hyperref anchor string when one exists. When an entity is materialized without `hyperref`, emit the key with the empty value `{}`. |
| `src` | Required | Required | Source location (see `src` format below) |
| `env` | Required for theorem atoms | Not used | Environment name (`theorem`, `lemma`, etc.) |
| `owner` | Not used | Required | Owning source atom ID. In `equations=all` or top-level `equations=outer`, this is the equation source atom `aN`. In `equations=outer`/`off` with no equation source atom, this is the fallback enclosing atom ID, or empty if no enclosing source exists. |

`anchor` is optional in the schema because some entities, especially forward-label proofs, do not have an anchor until their display is resolved. Once an entity's display is materialized, its `anchor` metadata is emitted in that same run, with the empty value when `hyperref` is absent.

**Note:** Proof parent/mode are NOT metadata keys. They use dedicated `\codep@proofparent` records, which carry structured data (parent atom ID + mode) that would be awkward to split across multiple `\codep@meta` calls. The `proofparent` record is loaded immediately at aux-read time and populates the proof's parent and anchor-mode fields directly.

<!-- Fixed: R2-NEW-MAJOR (no-hyperref empty anchor) -->
**Anchor emission rule:** Whenever an entity's display metadata is emitted, its `anchor` metadata is emitted in the same run. If `hyperref` is loaded, the value is the real anchor string. If `hyperref` is not loaded, the value is the empty string. This applies uniformly to theorem atoms, proof atoms, paragraph atoms, equation source atoms, and equation-label targets. No-hyperref runs therefore emit `\codep@meta{aN}{anchor}{}` / `\codep@meta{qK}{anchor}{}` instead of omitting the `anchor` key.

<!-- Fixed: MINOR 21 -->
**`src` format definition:** The `src` metadata value is `\jobname.tex:\the\inputlineno:1` -- that is, `filename:line:column` where the column is always `1` (TeX does not provide column information). This format is used identically in both `.aux` `\codep@meta{...}{src}{...}` records and `.cdp` `\codep@cdp@meta{...}{src}{...}` records. The capture happens at the hook site (e.g., `cmd/E/before` for theorems, `env/Q/begin` for equations, `para/begin` for paragraphs, `cmd/proof/before` for proofs) by expanding `\jobname.tex:\the\inputlineno:1` at write time.

#### Replay semantics

- `atomdecl`, `targetdecl`, `meta`, `labelentity` populate tables immediately.
- `refevent` queues unresolved label-based edges.
- `proofbind` queues unresolved proof label bindings.
- At `begindocument/end`:
  1. Flush proof-bind queue (resolve labels to entities; **ignore labels whose entity ID has no matching `atomdecl` or `targetdecl`** — same orphan check as ref-event flush; ineligible targets produce warnings)
  2. Flush ref-event queue: resolve each `(source-atom-id, target-label)` to `(source-atom-id, target-entity-id)`. **Ignore any `labelentity` record whose entity ID has no matching `atomdecl` or `targetdecl`.** This handles discarded equation labels from all-`\notag` blocks: the `labelentity` was written at `\label` time, but the `targetdecl` was never emitted because the block produced no numbers. Such orphan `labelentity` records are harmless stale data.
  3. Mark rerun-needed on any unresolved label

On compatible aux: load declarations and metadata immediately, then flush queues in order. On mismatch: suppress rendering, write fresh records, warn.

<!-- Fixed: R13b-MINOR — current-run writes also update in-memory tables -->
**Current-run writes update in-memory tables.** Aux replay populates tables from the previous run's `.aux` file. But current-run writes (e.g., `\codep@atomdecl`, `\codep@meta`, `\codep@labelentity` emitted during the current document traversal) ALSO update the same in-memory tables immediately at emit time. This is required for within-run resolution to work: `\codepproofof{label}` consults the live `label -> entity` map, which must contain labels defined earlier in the same run (not just from the previous run's `.aux`). Similarly, `\codep@bindproofparent` looks up parent metadata (display, anchor) from the in-memory `meta` table, which must already contain entries written earlier in the current run. The in-memory tables are therefore populated from two sources: aux replay (at `begindocument/before` / `begindocument/end`) and current-run emit hooks (during document traversal). Both sources write to the same tables; last-write-wins semantics apply (§2.6).

Changing `equations=all` to `equations=outer` between runs is well-defined: first run after the change ignores old equation-source records (config hash mismatch); second run reflects outer-mode fallthrough.

#### Before/after examples

**Theorem:**

<!-- Fixed: MINOR 19 -->
Current (Architecture A):
```tex
\codep@atomref{theorem:1.2}{thm:A}
\codep@anchormap{theorem:1.2}{atom.3}
\codep@lbltype{thm:A}{theorem}
```

New (Architecture B):
```tex
\codep@auxheader{3}{a7f3...}
\codep@atomdecl{a3}{theorem}
\codep@meta{a3}{display}{1.2}
\codep@meta{a3}{anchor}{atom.3}
\codep@meta{a3}{src}{main.tex:42:1}
\codep@meta{a3}{env}{theorem}
\codep@labelentity{thm:A}{a3}
\codep@refevent{a5}{thm:A}
```

**Equation (Track 1, `equations=all`):**

Current:
```tex
\codep@atomref{equation:1}{thm:main}
\codep@anchormap{equation:1}{equation.1}
\codep@lbltype{eq:use}{equation}
```

New:
```tex
\codep@atomdecl{a4}{equation}
\codep@meta{a4}{display}{(1)}
\codep@meta{a4}{anchor}{codep.eqsrc.4}
\codep@meta{a4}{src}{main.tex:131:1}
<!-- Fixed: R12-NEW-MINOR — equation target examples include required src metadata -->
\codep@targetdecl{q1}{equation}
\codep@meta{q1}{display}{(1)}
\codep@meta{q1}{anchor}{equation.1}
\codep@meta{q1}{src}{main.tex:131:1}
\codep@meta{q1}{owner}{a4}
\codep@labelentity{eq:use}{q1}
\codep@refevent{a4}{thm:main}
```

**Align (Track 2, multiple labels):**

Current:
```tex
\codep@atomref{equation:1--3}{thm:X}
\codep@anchormap{equation:1--3}{codep.eq.1}
\codep@lbltype{eq:a}{equation}
\codep@lbltype{eq:b}{equation}
\codep@lbltype{eq:c}{equation}
```

New:
```tex
\codep@atomdecl{a7}{equation}
\codep@meta{a7}{display}{(1--3)}
\codep@meta{a7}{anchor}{codep.eqsrc.7}
\codep@meta{a7}{src}{main.tex:55:1}
\codep@targetdecl{q3}{equation}
\codep@meta{q3}{display}{(1)}
\codep@meta{q3}{anchor}{equation.1}
\codep@meta{q3}{src}{main.tex:56:1}
\codep@meta{q3}{owner}{a7}
\codep@labelentity{eq:a}{q3}
\codep@targetdecl{q4}{equation}
\codep@meta{q4}{display}{(2)}
\codep@meta{q4}{anchor}{equation.2}
\codep@meta{q4}{src}{main.tex:57:1}
\codep@meta{q4}{owner}{a7}
\codep@labelentity{eq:b}{q4}
\codep@targetdecl{q5}{equation}
\codep@meta{q5}{display}{(3)}
\codep@meta{q5}{anchor}{equation.3}
\codep@meta{q5}{src}{main.tex:58:1}
\codep@meta{q5}{owner}{a7}
\codep@labelentity{eq:c}{q5}
\codep@refevent{a7}{thm:X}
```

**Proof (separated, `\codepproofof`):**

Current:
```tex
\codep@atomref{proof:1.1}{thm:target}
```

New:
```tex
\codep@atomdecl{a6}{proof}
\codep@meta{a6}{display}{1.1*}
\codep@meta{a6}{anchor}{atom.1}
\codep@meta{a6}{src}{main.tex:51:1}
\codep@proofparent{a6}{a1}{statement}
\codep@refevent{a6}{thm:target}
```

<!-- Fixed: R11-MAJOR — forward-label proof still gets standalone display/anchor on pass 1 -->
**Proof (forward label, unresolved on pass 1):**
On pass 1, `\codepproofof{lem:future}` can't resolve the label. The proof hits standalone fallback at `para/begin` or `cmd/endproof/before`, which assigns standalone display/anchor. At proof end, both the standalone metadata and the `proofbind` are serialized:

```tex
\codep@atomdecl{a9}{proof}
\codep@meta{a9}{display}{3.1*}
\codep@meta{a9}{anchor}{codep.proof.a9}
\codep@meta{a9}{src}{main.tex:80:1}
\codep@proofbind{a9}{lem:future}{proof}
```

On pass 2, the proof-bind queue resolves `lem:future` to its entity, and `\codep@proofparent` is written for the next run.

**Equation (outer mode inside theorem):**

No `\codep@atomdecl{a...}{equation}` is written. The `q...` target records still exist. Refs emit from the enclosing theorem/proof atom:
```tex
\codep@atomdecl{a2}{theorem}
\codep@meta{a2}{display}{1.1}
...
\codep@targetdecl{q1}{equation}
\codep@meta{q1}{display}{(1)}
\codep@meta{q1}{anchor}{equation.1}
\codep@meta{q1}{src}{main.tex:45:1}
\codep@meta{q1}{owner}{a2}
\codep@labelentity{eq:inner}{q1}
% no equation source atom -- refs attribute to a2
\codep@refevent{a2}{thm:X}
```

### 2.7 .cdp Protocol (v2)

Bump to `\codep@cdp@version{2}`. Atom-scoped records use atom IDs, not display numbers. Add explicit non-atom targets and ref events.

```tex
\codep@cdp@version{2}
\codep@cdp@source{\jobname.tex}

\codep@cdp@atom{a12}{lemma}
\codep@cdp@meta{a12}{display}{2.3}
\codep@cdp@meta{a12}{env}{lemma}
\codep@cdp@meta{a12}{src}{main.tex:84:1}
\codep@cdp@target{q7}{equation}
\codep@cdp@meta{q7}{display}{(4.1)}
\codep@cdp@meta{q7}{src}{main.tex:131:1}
\codep@cdp@label{a12}{lem:main}
\codep@cdp@label{q7}{eq:a}
\codep@cdp@ref{a19}{eq:a}
\codep@cdp@proofparent{a20}{a12}{statement}

\codep@cdp@tag{a12}{uid}{cat:category}
\codep@cdp@def{a12}{Hom}
\codep@cdp@use{a19}{Hom}
\codep@cdp@cmddef{Hom}{kind}{newcommand}

\codep@cdp@end{OK}
```
<!-- Fixed: R13b-MAJOR 3 — added \codep@cdp@meta{a12}{env}{lemma} to example; env key is required for theorem atoms -->

<!-- Fixed: R2-NEW-NITPICK (mandatory labels) -->
**Requirements:**
- `kind`, `display`, and `src` are mandatory for every emitted atom/target record that the CLI needs to resolve.
- `label` is mandatory only for label-addressable entities; unlabeled atoms legitimately have no `\codep@cdp@label{...}{...}` record.
- Equation labels appear as `target` records, never as `atom` records.
- `\codep@cdp@ref` is label-based so forward refs remain representable in one pass.
- Non-graph records unchanged: `source`, `cmddef`, `def`, `use`, `tag`, `end`.

<!-- Fixed: R2-BLOCKER 12 (proof relation records) -->
**Proof relation records:** v2 `.cdp` has two proof-relation records with different roles. `\codep@cdp@proofparent{proof-id}{parent-id}{mode}` is the normal resolved form and is emitted for every proof whose parent is known on this run, including adjacent proofs, immediately resolved `\codepproofof` bindings, and forward-label proofs once a later run resolves them. `\codep@cdp@proofbind{proof-id}{label}{mode}` is only a deferred-intent record for a forward-label proof whose label is still unresolved on this run. A single proof emits either `proofparent` or `proofbind` in one run, never both, and the CLI must use `proofparent` rather than inferring parentage from `display`.

**Before/after examples:**

Current v1:
```tex
\codep@cdp@version{1}
\codep@cdp@source{example.tex}
\codep@cdp@atom{1.1}{theorem}
\codep@cdp@proof{1.1*}
\codep@cdp@label{1.1}{thm:main}
\codep@cdp@end{OK}
```

<!-- Fixed: BLOCKER 12 — resolved proof uses proofparent, not proofbind -->
<!-- Fixed: R13b-MAJOR 3 — added env metadata to theorem atom in New v2 example -->
New v2:
```tex
\codep@cdp@version{2}
\codep@cdp@source{example.tex}
\codep@cdp@atom{a1}{theorem}
\codep@cdp@meta{a1}{display}{1.1}
\codep@cdp@meta{a1}{env}{theorem}
\codep@cdp@label{a1}{thm:main}
\codep@cdp@atom{a2}{proof}
\codep@cdp@meta{a2}{display}{1.1*}
\codep@cdp@proofparent{a2}{a1}{statement}
\codep@cdp@end{OK}
```

The v1-only `\codep@cdp@proof` emission path is removed entirely.

### 2.8 Rendering Query API

Tracking owns all graph tables. Rendering does not read `brnode`, `brcount`, `labelentity`, `meta`, or anchors directly.

Tracking exports exactly:

```tex
\def\codep@graph@hasrefs#1#2#3{...}      % #1=target-id, #2=then, #3=else
\def\codep@graph@getdisplay#1#2{...}     % #1=entity-id, #2 <- display string
\def\codep@graph@getanchor#1#2{...}      % #1=entity-id, #2 <- anchor or \@empty
\def\codep@graph@getkind#1#2{...}        % #1=entity-id, #2 <- kind string
\def\codep@graph@foreachref#1#2{...}     % #1=target-id, #2=callback{source-id}
```

<!-- Fixed: R2-MAJOR 14 -->
**Render-layer hook contract:**
- Theorem/proof/paragraph hooks receive **atom IDs**, not prefixed display keys.
- Equation rendering receives `\codep@render@equationblock{source-atom-id}{fallback-atom-id}{\do{q1}\do{q2}...}` at `env/.../after`.
- `source-atom-id` is the equation source atom when the block owns refs; otherwise it is empty.
- `fallback-atom-id` is the enclosing source atom when refs fall through to an enclosing theorem/proof/paragraph; otherwise it is empty.
- In `equations=all`, pass `{aN}{}`. In top-level `equations=outer`, also pass `{aN}{}`. In nested `equations=outer`, pass `{}{<enclosing-aN>}`. In `equations=off`, pass `{}{<enclosing-aN>}` when an enclosing source exists, else `{}{}`.
- Rendering must use only these explicit arguments plus the query API; it must not inspect tracking internals to rediscover the enclosing owner.
- Rendering formats source displays by calling `getdisplay`/`getanchor` per source ID.

This removes all parsing of `type:number` strings from `codependent-render.sty`.

### 2.9 Dedup Semantics

Two-stage dedup:

1. **Write-time** (during document traversal): keyed by `(source-atom-id, raw-label)`. Suppresses duplicate writes from `\@setref` + `\cref@getlabel` + hyperref wrappers that fire for the same logical reference.

2. **Replay-time** (when loading `.aux` on pass 2): keyed by `(source-atom-id, resolved-target-entity-id)`. Collapses multiple labels that point to the same theorem atom, but keeps distinct equation labels distinct (different `qK` IDs resolve to different entity IDs even if they share an `aN` source).

### 2.10 Proof Binding

<!-- Fixed: R13 — adjacency text notes nested-proof exception -->
**Adjacent proofs:** If `\codep@pendingresultid` is non-empty when a proof begins AND the proof is NOT nested (i.e., `\codep@currentproofid` was empty before this proof), bind immediately to that atom with mode `statement`. Clear pending result. Nested proofs never auto-bind — see §2.4.

<!-- Fixed: R2-NEW-MINOR (\codepproofof ineligible label) -->
<!-- Fixed: R5/R10 — codepproofof calls bindproofparent (memory + metadata only; .aux/.cdp deferred to proof end) -->
<!-- Fixed: R5-NEW-MAJOR — proof-mode hypertarget placement on converged pass-2 runs -->
<!-- Fixed: R6 — codepproofof always runs (overrides preloaded parent), fixes stale-parent bug, anchor emission via bindproofparent -->
**`\codepproofof{label}` / `\codepproofof*{label}`:** This macro runs **unconditionally** — it is NOT gated on `\ifcodep@proofdisplaypending`. This is critical for two reasons: (a) proof-mode anchor placement must happen at the call site on every pass, and (b) a changed `\codepproofof` argument must override a stale preloaded parent from a previous run. Consult the live `label -> entity` map:

<!-- Fixed: R11-MAJOR — successful bind clears any pending proofbind marker -->
<!-- Fixed: R12 — live codepproofof also checks entity has a declaration (atomdecl/targetdecl) -->
<!-- Fixed: R13b-MAJOR 6 — proof atoms are explicitly proof-eligible -->
**Proof-eligible entities for `\codepproofof`.** An entity is proof-eligible if and only if it has a matching `atomdecl` with `kind` equal to `theorem`, `lemma`, `definition`, or any other tracked theorem-like environment name — OR with `kind` equal to `proof`. **A label pointing to a proof atom IS proof-eligible.** Proofs can be chained: `\codepproofof{lab}` where `lab` labels a proof atom `aK` is valid and sets `aK` as the parent of the current proof. This allows proof-of-proof attribution. Non-eligible entities are `qK` equation targets (kind `equation` with a `q` prefix) and paragraph atoms (kind `paragraph`).

- If the label resolves to an entity ID that has a matching `atomdecl` or `targetdecl` AND is proof-eligible:
  - `\codep@bindproofparent{<proof-id>}{<parent-atom-id>}{statement|proof}` — this **overrides** any earlier binding (including a preloaded one from aux replay) AND **clears any pending `proofbind` marker** so that `cmd/endproof/before` will serialize `proofparent` only, not both. It stores in memory and emits `display`/`anchor` metadata. Serialization to `.aux`/`.cdp` is deferred to `cmd/endproof/before`.
  - For `statement` mode: emits `\codep@meta{aN}{anchor}{<parent-anchor>}` (or `{}` if hyperref not loaded)
  - For `proof` mode (`\codepproofof*`): create `\hypertarget{codep.proof.aN}{}` at the current call site (if hyperref loaded). Emits `\codep@meta{aN}{anchor}{codep.proof.aN}` (overrides any earlier anchor). If hyperref not loaded, emits `\codep@meta{aN}{anchor}{}`.
  - If `\ifcodep@proofdisplaypending` was true, clear it now
  - **Stale-parent convergence:** On pass 2, if the user changed the `\codepproofof` target, this fresh binding overwrites the stale preloaded parent. The `.aux` gets the new `proofparent` record. Pass 3 converges. This matches standard LaTeX rerun semantics.
<!-- Fixed: R7-MAJOR — unknown/ineligible codepproofof must invalidate stale preloaded parent -->
- If the label is known but resolves to a non-proof-eligible entity (e.g., a `qK` equation target or a paragraph atom):
  - Emit `\PackageWarning{codependent}{\string\codepproofof: label '<label>' does not name a proof-eligible entity}`
  - **Invalidate** any preloaded/adjacent parent that was applied at proof-begin: clear the proof-parent table entry for this proof ID, and set `\codep@proofdisplaypendingtrue` (forces re-evaluation at fallback points)
  - Since serialization is deferred to `cmd/endproof/before`, the stale parent never reaches `.aux`
  - Do NOT mark a `proofbind` (the label IS known, just ineligible)
- If the label is not yet known:
  - **Invalidate** any preloaded/adjacent parent: clear the proof-parent table entry, set `\codep@proofdisplaypendingtrue`
  - Mark an unresolved `proofbind{<proof-id>}{<label>}{<mode>}` for deferred serialization at `cmd/endproof/before`

<!-- Fixed: R2-BLOCKER 6 -->
**Operational resolution order for proof display/anchor:** The proof display state is decided in exactly this order, and later steps run only while `\ifcodep@proofdisplaypending` is still true.

1. **Proof begin:** `cmd/proof/before` allocates the proof atom and first checks whether aux replay already loaded a resolved `proofparent` for this proof ID.
2. **Adjacency:** if no replay-loaded parent exists, `cmd/proof/before` checks `\codep@pendingresultid`; a non-empty value binds the proof immediately in `statement` mode.
3. **Pending state:** only if both checks fail does the proof remain pending (`\codep@proofdisplaypendingtrue`).
4. **Explicit `\codepproofof`:** `\codepproofof{label}` / `\codepproofof*{label}` runs unconditionally (not gated on pending). If the proof was already settled at step 1 or 2, `\codepproofof` overrides that binding with a fresh one. This handles stale-parent convergence when the user changes the `\codepproofof` argument between runs.
5. **First proof paragraph:** the first `para/begin` inside the proof re-checks whether the current proof ID now has a resolved parent. If so, it applies that binding and clears the pending flag. If not, it assigns standalone proof display/anchor and clears the pending flag.
6. **Proof end:** `cmd/endproof/before` performs the same re-check as a last chance for empty proofs or proofs with no paragraph-open event. Only if the proof is still unresolved after this re-check does it assign standalone proof display/anchor.

The re-check in steps 5 and 6 is a lookup of the current proof ID in the resolved proof-parent table, followed by `\codep@bindproofparent` if found. It is not a second raw-label parse. This is what makes pass-2 convergence work: on pass 2, a `proofparent` resolved from pass 1 is already loaded before the proof begins, so step 1 clears the pending flag and steps 5-6 never overwrite the proof with standalone metadata.

**Nested proofs:** Never auto-adjacent. Must not consume outer `\codep@pendingresultid`.

**Nested theorem-like envs inside a proof:** Still allocate their own atoms normally.

### 2.11 Restatable Replay

<!-- Fixed: MAJOR 15 -->
Detection: replay is when `\csname c@<basecounter>\endcsname` is no longer `\c@atom` (the current alias test is preserved).

**Shared-counter restriction:** This replay detection is correct ONLY for tracked environments that share the aliased base counter (i.e., environments whose counter was aliased to `atom` by `\codeptrack`). Independently numbered tracked environments (those using a separate counter not aliased to `atom`) would always appear to be in replay mode under this test. This is the current design constraint and is acceptable: all standard tracked theorem-like environments share the `atom` counter via aliasing, and the `restatable` package also uses this aliased counter. If a future extension adds tracked environments with independent counters, replay detection must be extended (e.g., per-environment replay flags).

Replay semantics:
- Increment `replaydepth` and `suppressdepth`
- No atom allocation
- No label ownership records
- No ref events
- No `.cdp` atom/target/ref records

On `cmd/endE/before` in replay: decrement `replaydepth` and `suppressdepth`.

### 2.12 Config Hash and Stale Aux

<!-- Fixed: BLOCKER 7 -->
The `.aux` header record `\codep@auxheader{3}{<hash>}` carries a config hash computed from:
- Set of tracked environments
- `paragraphs` option value
- `proofs` option value
- `equations` option value (all/outer/off)
- Registered equation environments
- Numbering depth

**`\codep@auxheader` must be the FIRST codependent record in the `.aux` file.** All codependent graph records are written after the header. On `.aux` read-back, the header handler sets an internal compatibility flag that gates ALL subsequent codependent record handlers.

**On compatible header:** Set the compatibility flag to true. All subsequent `atomdecl`, `targetdecl`, `meta`, `labelentity`, `refevent`, `proofparent`, and `proofbind` handlers load data normally.

**On mismatch or missing header:**
- Set the compatibility flag to **false**
- **Ignore ALL subsequent codependent graph records** -- not just suppress rendering, but skip loading entirely. Stale `labelentity`, `proofparent`, `refevent`, and `owner` data must never enter the in-memory tables, because incompatible IDs from a previous configuration would corrupt proof binding, equation ownership, and dedup.
- Write fresh records from scratch during this run
- Issue `\PackageWarningNoLine{codependent}{Configuration changed; rerun to update backreferences}`

The `\providecommand` no-op definitions for old `.aux` macros (`\codep@atomref`, `\codep@anchormap`, `\codep@lbltype`) ensure that one stale old `.aux` run does not hard-error, but they never populate any graph tables.

This makes option changes between runs well-defined without requiring manual aux deletion.

## 3. Migration Waves

### Wave 1: Render Barrier

**Goal:** Move `codependent-render.sty` off raw graph internals before any graph storage changes.

**Scope:** Touch only `codependent.sty` and `codependent-render.sty`.

**What changes:**
- Add the five query API macros in `codependent.sty` (`\codep@graph@hasrefs`, `\codep@graph@getdisplay`, `\codep@graph@getanchor`, `\codep@graph@getkind`, `\codep@graph@foreachref`) as shims over the current prefixed-key graph.
<!-- Fixed: R13b-MAJOR 7 — \codep@render@equationblock added to Wave 1 scope -->
- Add `\codep@render@equationblock{source-atom-id}{fallback-atom-id}{\do{q1}\do{q2}...}` to `codependent.sty` as a shim that calls existing render internals. This is part of the render barrier: `codependent-render.sty` must call `\codep@render@equationblock` (not access equation internals directly) starting from Wave 1. The shim implementation in Wave 1 can forward to current render helpers; the real implementation lands in Wave 2/3.
- In `codependent-render.sty`, replace all direct reads inside `\codep@collapsebr`, `\codep@queuebackref`, `\codep@appendix@emit`, and `\codep@brhyper` to go through the query API.
- Delete all direct `\csname codep@brcount@...\endcsname`, `\csname codep@brnode@...\endcsname`, and `\csname codep@anchor@...\endcsname` access paths from `codependent-render.sty`.

**What does NOT change:**
- The graph still uses current prefixed keys (`theorem:1.2`) as temporary entity IDs.
- No `.aux` or `.cdp` changes.
- `\codep@brlast@...` stays internal writer state; render never needs it.

**Test impact:** Zero fixture edits. All tests remain byte-for-byte green.

**Verification criteria:**
<!-- Fixed: MINOR 18 -->
1. Full test suite passes (currently 94 tests).
2. `codependent-render.sty` no longer references `codep@brcount@`, `codep@brnode@`, or `codep@anchor@` directly (verified by grep).

**Risk:** Low. Only failure mode is render regressions in appendix/hyperlink code. Rollback is a single commit revert with no test churn.

### Wave 2: State Machine Replacement

**Goal:** Make the new atom/context model authoritative for theorem/proof/paragraph lifecycle while preserving current `.aux` and `.cdp` output exactly.

**Scope:** Touch `codependent.sty` only.

**What changes:**
- Replace Section 4 state (all variables listed in Section 2.2 "What is removed" above) with the new runtime state.
- Implement `\codep@allocatomid`, `\codep@alloctargetid`, `\codep@ctxpush`, `\codep@ctxpop`, `\codep@ctxpeekid`, `\codep@ctxpeekkind`, `\codep@closeparagraphifopen`.
- Introduce `\codep@writerefevent` and `\codep@recordlabelowner`, but keep their backends emitting legacy `\codep@atomref` / `\codep@lbltype` / `\codep@anchormap`.
- Rework all callers: `\codep@hooktheorem@begin/@after/@record/@end`, `\codep@hookproof@begin`, `\codep@proof@standalone`, `\codep@proof@materialize`, `\codep@proof@adjacent`, `\codep@hookproof@end`, `\codep@proofof@do`, `\codep@parahook@paragraph`, `\codep@installparahook`, `\codep@trackeqenv`, `\codep@trackalignenv`.

**What does NOT change:**
- `.aux` wire format (still `\codep@atomref`, `\codep@anchormap`, etc.)
- `.cdp` wire format (still v1)
- Wave 1 render shim (still backed by prefixed keys)
- New state computes old prefixed keys at the serialization boundary

**Test impact:** Zero fixture edits if done correctly. This wave is wire-format-invisible.

**Verification criteria:**
1. Full test suite passes.
2. Focused reruns of `test-currentatom-clear`, all `test-proofs-*`, `test-restatable-single`, and all `test-equations-*`.
3. For at least one theorem/proof fixture and one equation fixture, diff produced `.aux` and `.cdp` against pre-wave outputs; they must match.

**Risk:** Medium. The danger is off-by-one lifecycle bugs around adjacent proofs, first-paragraph proof materialization, and restatable replay. Rollback is clean because no test files changed.

### Wave 3: .aux Cutover

**Goal:** Land the real graph redesign: opaque atom/target IDs, label ownership, resolved-pair dedup, and proof binding in `.aux`.

**Scope:** Touch `codependent.sty` and the exact **44 fixtures** whose current headers mention `\codep@atomref`, `\codep@anchormap`, or `\codep@lbltype`.

**What changes:**
- Add `\codep@targetid`, `\codep@alloctargetid`, active/passive handlers for all new aux record types (`atomdecl`, `targetdecl`, `meta`, `labelentity`, `refevent`, `proofparent`, `proofbind`).
- Add `\codep@auxheader` with config hash.
- Rewrite `\codep@writerefevent` and `\codep@recordlabelowner` to emit new records.
- Remove old read/write path: active `\codep@atomref`, `\codep@lbltype`, `\codep@anchormap`, `\codep@writeatomref*`, `\codep@writelbltype`, `\codep@dedupwrite`, `\codep@processbr`, `\codep@appendbr`, `\codep@extractlblnum`, `\codep@extractanchor`, and `\newlabel`-driven target reconstruction.
- Equation labels become `q...` targets; equations become source atoms; align-range identity (`equation:1--3`) stops existing.
- `\codepproofof` gets pass-2 settlement through `proofbind`/`proofparent`.
- Keep `\providecommand` no-op definitions for old aux macros so one stale old `.aux` run does not hard-error; they must not remain active graph inputs.

**What does NOT change:**
- `.cdp` format (still v1 in this wave)
- Non-graph `.aux` records (concept `cmddef`/`def`/`use` untouched)
- The Wave 1 query API adapts to the new storage transparently

**Test impact:** Update **~125 aux assertions** in 44 fixtures: ~108 `atomref`, ~15 `anchormap`, ~2 `lbltype`. Leave concept assertions unchanged.
- 22 fixtures are straightforward renames (theorem/paragraph atomref -> atomdecl+meta+refevent)
- 22 need manual review (equation ranges, proof anchors, negative assertions)

**Example assertion transformation:**

Before:
```
%% TEST-AUX-CONTAINS: \codep@atomref{theorem:1.2}{thm:A}
%% TEST-AUX-CONTAINS: \codep@anchormap{1.2}{atom.3}
```

After:
```
%% TEST-AUX-CONTAINS: \codep@atomdecl{a3}{theorem}
%% TEST-AUX-CONTAINS: \codep@meta{a3}{display}{1.2}
%% TEST-AUX-CONTAINS: \codep@meta{a3}{anchor}{atom.3}
%% TEST-AUX-CONTAINS: \codep@labelentity{thm:A}{a3}
%% TEST-AUX-CONTAINS: \codep@refevent{a5}{thm:A}
```

Before (equation):
```
%% TEST-AUX-CONTAINS: \codep@atomref{equation:1}{thm:main}
%% TEST-AUX-CONTAINS: \codep@anchormap{equation:1}{equation.1}
%% TEST-AUX-NOT-CONTAINS: \codep@atomref{1.1}{thm:main}
```

After (equation):
```
%% TEST-AUX-CONTAINS: \codep@atomdecl{a4}{equation}
%% TEST-AUX-CONTAINS: \codep@meta{a4}{display}{(1)}
%% TEST-AUX-CONTAINS: \codep@targetdecl{q1}{equation}
%% TEST-AUX-CONTAINS: \codep@labelentity{eq:use}{q1}
%% TEST-AUX-CONTAINS: \codep@refevent{a4}{thm:main}
%% TEST-AUX-NOT-CONTAINS: \codep@atomref
```

<!-- Fixed: MAJOR 17 (Wave 3 verification) -->
**Verification criteria:**
1. Full test suite passes.
2. Key targeted fixtures: `test-equations-track1`, `test-equations-track2-align`, `test-equations-consecutive-align`, `test-trackalign-user`, `test-proofs-separated`, `test-proofs-as-backref-target`, `integ-full-stack-inline`, `integ-full-stack-below`, `trinity-test`.
3. Existing PDF assertions are the render safety net.
4. **New record type assertions are mandatory.** The updated fixture assertions (the ~125 aux assertion rewrites) ARE the graph-protocol test coverage. Each rewritten assertion checks for the new record types (`atomdecl`, `targetdecl`, `meta`, `labelentity`, `refevent`, `proofparent`, `proofbind`). PDF output alone does not validate the graph protocol -- a broken `auxheader`, wrong `proofparent`, missing `owner`, or absent `refevent` can leave PDFs looking correct while the graph is silently wrong. The fixture updates serve double duty: they are both the migration step and the verification step.

**Risk:** HIGH. This is the semantic flip point. The two biggest hazards are:
1. Mis-binding proof parents (wrong atom ID in `\codep@proofparent`)
2. Losing equation target distinctness (two labels in one align collapsing to one entity)

Rollback must revert code AND the 44 fixture updates together.

### Wave 4: .cdp Cutover

**Goal:** Move the sidecar from display-number records to opaque-ID records without changing rendering.

**Scope:** Touch `codependent.sty` and the exact **74 fixtures** whose current headers mention `\codep@cdp@version{1}`, `\codep@cdp@atom`, `\codep@cdp@proof`, `\codep@cdp@meta`, or `\codep@cdp@label`.

<!-- Fixed: R2-BLOCKER 12 (cdp cutover What changes) -->
**What changes:**
- Change open hook to `\codep@cdp@version{2}`.
- Rewrite emit sites in `\codep@hooktheorem@record`, `\codep@parahook@paragraph`, the label wrapper, and `cmd/endproof/before` (proof serialization point) to emit ID-based records.
- **Add new emit sites:**
  - **Equation-target emission:** At `env/Q/after`, emit `\codep@cdp@target{qK}{equation}`, `\codep@cdp@meta{qK}{display}{...}`, `\codep@cdp@meta{qK}{src}{...}`, and `\codep@cdp@label{qK}{eq:...}` for each buffered equation label.
  - **Equation-source atom emission:** At `env/Q/after` (when block produced a number), emit `\codep@cdp@atom{aN}{equation}`, `\codep@cdp@meta{aN}{display}{(N--M)}`, `\codep@cdp@meta{aN}{src}{...}`.
  - **Graph-ref emission:** At ref interception time, emit `\codep@cdp@ref{aN}{label-key}` for each `\codep@writerefevent` call. (Buffered equation refs emit at `env/Q/after` alongside the `.aux` ref events.)
- **Proof relation emission:** All proof `.cdp` records are written at `cmd/endproof/before` (the single serialization point, matching `.aux`). Emit `\codep@cdp@proofparent{proof-id}{parent-id}{mode}` if a binding was resolved during this proof. Emit `\codep@cdp@proofbind{proof-id}{label}{mode}` only if the binding remains unresolved. Standalone proofs emit neither. Pass-2 settlement changes a proof from `proofbind` to `proofparent`.
- Remove v1-only `\codep@cdp@proof` emission path.
- Keep non-graph records unchanged: `source`, `cmddef`, `def`, `use`, `tag`, `end`.

**What does NOT change:**
- `.aux` format (already v2 from Wave 3)
- Rendering (uses query API, not .cdp)
- Non-graph `.cdp` records

**Test impact:** Update **~175 graph-shaped .cdp assertions** in 74 fixtures: ~7 version markers, ~136 atom assertions, ~15 proof assertions, ~3 env-meta assertions, ~14 label assertions. Leave ~94 `@cdp@end` assertions unchanged and `cmddef`/`def`/`use`/`tag` assertions unchanged.
- 48 fixtures are mostly systematic `display -> atom+meta(display)` rewrites
- 26 need manual review (proofs, labels, version, env metadata)

**Example assertion transformation:**

Before:
```
%% TEST-CDP-CONTAINS: \codep@cdp@version{1}
%% TEST-CDP-CONTAINS: \codep@cdp@atom{1.1}{theorem}
%% TEST-CDP-CONTAINS: \codep@cdp@proof{1.1*}
%% TEST-CDP-CONTAINS: \codep@cdp@label{1.1}{thm:main}
```

<!-- Fixed: BLOCKER 12 — Wave 4 fixture: resolved proof uses proofparent, not proofbind -->
After:
```
%% TEST-CDP-CONTAINS: \codep@cdp@version{2}
%% TEST-CDP-CONTAINS: \codep@cdp@atom{a1}{theorem}
%% TEST-CDP-CONTAINS: \codep@cdp@meta{a1}{display}{1.1}
%% TEST-CDP-CONTAINS: \codep@cdp@atom{a2}{proof}
%% TEST-CDP-CONTAINS: \codep@cdp@meta{a2}{display}{1.1*}
%% TEST-CDP-CONTAINS: \codep@cdp@proofparent{a2}{a1}{statement}
%% TEST-CDP-CONTAINS: \codep@cdp@label{a1}{thm:main}
```

<!-- Fixed: MAJOR 17 (Wave 4 verification) -->
**Verification criteria:**
1. Full test suite passes.
2. Focus on `test-sbl-version-source`, `test-base-counter-custom`, `test-label-kernel`, `test-label-cleveref-opt`, `test-proofs-inherit`, `test-proofs-after-non-result`, `test-proofs-paragraph-breaks-adjacency`, `integ-full-stack-below`.
3. **New .cdp record type assertions are mandatory.** The ~175 assertion rewrites must check for `\codep@cdp@atom{aN}{kind}`, `\codep@cdp@target{qK}{kind}`, `\codep@cdp@meta{...}{display}{...}`, `\codep@cdp@ref{...}{...}`, `\codep@cdp@proofparent{...}{...}{...}`, and `\codep@cdp@proofbind{...}{...}{...}`. Resolved proofs are validated through `proofparent`; only genuinely unresolved forward-label proofs use `proofbind`.

**Risk:** Medium-high. Main failure mode is under-specifying display metadata so formerly simple `@atom{1.2}{theorem}` tests lose semantic coverage. Rollback reverts code and the 74 fixture edits together.

### Wave 5: Cleanup

**Goal:** Remove active prefixed-key compatibility, making the active path opaque-ID-only everywhere including appendix traversal.

**Scope:** Touch `codependent.sty` and `codependent-render.sty`.

**What changes:**
- Change `\codep@registeratom` and appendix walk so atom registry stores entity IDs, not `{type:number}` pairs.
- Update `\codepappendix` / `\codep@appendix@emit` to get kind/display/refs only through the query API.
- Remove active-path legacy helpers: `\codep@splitprefix`, `\codep@displayfromkey`, and any `legacykey` alias tables that exist only to support pre-v2 graph.
- Keep only stale-aux compatibility no-ops for one-pass upgrade tolerance.

**What does NOT change:**
- `.aux` format (already v2)
- `.cdp` format (already v2)
- Test fixtures (should require zero edits if earlier waves were clean)

**Test impact:** Zero fixture edits.

**Verification criteria:**
1. Full test suite passes.
2. Code grep proves active path no longer depends on `type:number` graph keys.
3. `integ-appendix.lvt` is the most important regression target.

**Risk:** Low-medium. Likely breakage is appendix output order or missing display text. Rollback is isolated because no tests change.

## 4. Invariants

These must be true at ALL times during migration, after every wave:

1. **Full test suite passes.** No wave is committed unless all tests are green.
2. **One truth per subsystem.** At no point do old and new aux edge records both serve as active graph inputs. Passive no-op readers for stale old aux are fine; active dual-write is not.
3. **Atom identity is opaque.** After Wave 2, no semantic logic depends on parsing display strings out of atom identifiers.
4. **Rendering reads only through the query API.** After Wave 1, `codependent-render.sty` never touches `brcount`, `brnode`, `anchor`, `labelentity`, or `meta` tables directly.
5. **No semantic state depends on TeX group unwinding.** All graph-relevant state is explicit global state.
<!-- Fixed: MAJOR 16 -->
6. **Equation labels are always distinct targets (from Wave 3 onward).** Two `\label`s in the same `align` always produce different `qK` IDs. In Waves 1-2, the legacy format is preserved and equation labels use the old `equation:N` key scheme; the distinct-target invariant applies to the internal state model introduced in Wave 2 but is not visible in the wire format until Wave 3.
7. **`\codepproofof` never changes proof ID.** It changes proof metadata only.
8. **Dedup is by resolved pair.** After Wave 3, `(source-atom-id, target-entity-id)` is the dedup key, not label text.
9. **Restatable replay produces no records.** No atom allocation, no label ownership, no ref events, no `.cdp` atom/target/ref records during replay.
10. **Config hash gates rendering.** After Wave 3, a config mismatch suppresses rendering and forces rerun rather than rendering with stale data.
11. **Paragraph open/close is idempotent.** `\codep@closeparagraphifopen` is safe to call anywhere; `para/end` only pops when `\ifcodep@paragraphopen`.
12. **No wave relies on the next wave.** Each wave leaves a fully functional, shippable package.

## 5. Known Risks and Mitigations

### High risk

**Proof parent mis-binding (Wave 3).** The `\codep@pendingresultid` mechanism must be typed, explicit, and cleared only at defined boundary hooks. Adjacent proof detection is the single most fragile interaction in the package.
<!-- Fixed: R11-MINOR — all tracked envs are proof-eligible; non-result envs do NOT clear pending -->
- *Mitigation:* Focused test battery on all `test-proofs-*` fixtures after Wave 2 state machine is live. Verify that ALL tracked environments (including definitions, remarks, etc.) set `pendingresultid` and that proofs after non-result environments inherit adjacency (matching `test-proofs-after-non-result.lvt` expectations).

**Equation target distinctness loss (Wave 3).** If the dedup collapses two labels in the same `align` to one entity, equation-level backrefs break silently.
- *Mitigation:* Explicit test asserting `\codep@targetdecl{q3}{equation}` and `\codep@targetdecl{q4}{equation}` are both present for a two-label align.

**44-fixture bulk rewrite atomicity (Wave 3).** If the code change and fixture updates get out of sync, the suite is broken and diagnosis is expensive.
- *Mitigation:* Generate concrete new assertion lines from a green run first, then review equation/proof/negative-assertion files manually. Commit code and fixtures together. Rollback is the entire commit.

### Medium risk

**Off-by-one lifecycle bugs (Wave 2).** Adjacent proofs, first-paragraph proof materialization, and restatable replay are the three spots most likely to break.
- *Mitigation:* Diff `.aux` and `.cdp` output for at least one theorem/proof and one equation fixture before and after Wave 2; they must be identical.

**Verbose .aux protocol.** The new protocol writes significantly more lines per entity than the old one. For large documents this could slow compilation.
- *Mitigation:* This is an encoding concern, not a model concern. If size becomes an issue, collapse `decl + common meta` into a compact declaration record. That is a future optimization, not a Wave 3 blocker.

**Opaque IDs are harder to debug.** `a12` and `q7` are not self-explanatory in logs.
- *Mitigation:* Emit readable mappings in `\PackageInfo` output or a `.codepdbg` sidecar: `a12 -> lemma 2.3`, `q7 -> equation label (1)`. This is a debug convenience, not part of the identity model.

### Low risk

**Render regressions in appendix/hyperlink code (Wave 1).** The query API shim could have subtle differences from direct access.
- *Mitigation:* Zero fixture edits expected; any regression is immediately visible.

**Appendix output order (Wave 5).** Switching from `{type:number}` to entity IDs in the atom registry could change iteration order.
- *Mitigation:* `integ-appendix.lvt` is the primary regression target.

## 6. What Was Rejected and Why

### No hybrid architectures

The blind comparison suggested a "B-style architecture with A-style simplifications" as a possible hybrid. We rejected this. Architecture B with the equation-fix revision is the target. There is no mixing of A's `type:displaynumber` identity with B's opaque IDs. The identity model is opaque, period.

### No parallel old+new state

The migration plan explicitly warns against a "parallel state" wave. Running old state variables alongside new ones is the big-bang pattern in smaller form. Every new abstraction becomes live in the same wave it is introduced; every subsystem it replaces is removed in that same wave.

### No big-bang rewrite

A big-bang rewrite was attempted and reverted (documented in HISTORY.md). The five-wave approach exists specifically because the big-bang approach failed. Each wave is independently committable and revertable.

### No equations-never-source

Architecture B as originally written stated "Equations are NEVER source atoms." The blind comparison identified this as a direct mismatch with the requirements. The equation-fix revision corrects this: numbered equation environments ARE source-capable atoms (getting `aN` IDs), while equation labels remain distinct targets (getting `qK` IDs). The two ID spaces are preserved.

### No unified entity ID space

The equation-fix revision considered unifying `a` and `q` into a single `e` space. This was rejected because it does not remove the need for two different objects per multi-line display (one source atom, many label targets), so it adds churn without solving the hard part.

### No per-row source atoms for Track 2

One source atom per numbered line in an `align` was considered. Rejected in favor of one source atom per display block, because the source unit is the syntactic block and per-row identity requires fragile per-row patching. If sparse `\notag` layouts later need exact displays, add member-span metadata rather than changing the identity model.

### No content-hash staleness detection

The config hash covers package options only, not document content. Content-level staleness is handled by `rerunfilecheck` and LaTeX's own rerun mechanism. This was a previous design mistake documented in HISTORY.md.
