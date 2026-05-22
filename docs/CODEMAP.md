# CODEMAP.md — agent-facing reference

Purpose: this is an agent-facing lookup map, distinct from the human-narrative
`docs/DESIGN.md`. Cite it from future agent briefs to short-circuit explorer
macro hunts and make cold-start readings cheaper. Design intent is recorded in
`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_agent_facing_codemap.md`.

## Contents

- [User-facing API](#user-facing-api) `<deferred>`
- [Proof-attribution rail](#proof-attribution-rail) worked section
- [Anchormap rail](#anchormap-rail) `<deferred>`
- [Backref-rendering rail](#backref-rendering-rail) `<deferred>`
- [Pass orchestration](#pass-orchestration) `<deferred>`
- [Baseline ratchet](#baseline-ratchet) `<deferred>`
- [Suppression surface](#suppression-surface) `<deferred>`

## User-facing API
<deferred — see project_codemap_future_wave.md>

## Proof-attribution rail

### Behavior cross-reference

This rail implements or protects the proof behaviors in `docs/BEHAVIOR.md`:
`B-PROOF-ADJ`, `B-PROOF-OPAQUE-ID`, `B-PROOF-JOINT`,
`B-PROOF-HEADING-OVERRIDE`, `B-PROOF-DELAYED-COMMIT`, and
`B-PROOF-UNRESREF`. Related public behavior: explicit separated proofs are
`B-PROOF-SEP`; conflict warnings are governed by `B-WARN-ATTR-CONFLICTS`.

### Macro inventory

| Macro | Citation | Role |
|---|---:|---|
| `\ifcodep@proof@adjcommit@needed` | `codependent.sty:280` | Global sentinel: an adjacent proof candidate exists and must either be committed or cleared. |
| `\codep@proof@maybeheadingoverrideadjacent` | `codependent.sty:884` | D3 override hook: the first tracked heading target supersedes a conflicting physically-adjacent target and may warn. |
| `\codep@bindproofparent` | `codependent.sty:957` | Final attribution writer for adjacent/manual/joint parents; sets opaque `proof:a<N>` identity and appends target metadata. |
| `\codep@autoproofof@routeforward` | `codependent.sty:1593` | Forward-ref routing for heading labels that are not yet resolvable; allocates/routes through `unresref:<N>`. |
| `\codep@autoproofof@dispatchlabel` | `codependent.sty:1622` | Per-label dispatcher used after heading scan; resolves same-run tracked labels or calls routeforward. |
| `\codep@autoproofof@scan` | `codependent.sty:1640` | Heading content scan coordinator; collects `\ref`/`\autoref`/`\cref` labels, then dispatches each. |
| `\codep@autoproofof@heading` | `codependent.sty:1745` | Proof-heading entrypoint patched into `proof`; scans heading, finalizes adjacent candidate, captures proof anchor. |
| `\codep@proof@adjacent` | `codependent.sty:2088` | Adjacent path entry: stages the pending result as a delayed candidate instead of committing immediately. |
| `\codep@proof@adjcandidate@clear` | `codependent.sty:2115` | Clears per-proof staged adjacent-candidate csnames. |
| `\codep@proof@adjcandidate@drop` | `codependent.sty:2126` | Drops a staged adjacent candidate and clears adjacent-target/display state. |
| `\codep@proof@adjacent@commit` | `codependent.sty:2137` | Commits a staged adjacent binding through `\codep@bindproofparent`, queues rendering, clears candidate state. |
| `\codep@proof@adjacent@finalize` | `codependent.sty:2150` | End-of-heading finalizer: if the sentinel remains set, commits the current proof's staged candidate. |
| `\codep@autoproofof@resolve` | `codependent.sty:5114` | Auto-heading resolver shim; delegates to the shared resolver with auto mode enabled. |
| `\codep@proofof@resolve@inner` | `codependent.sty:5122` | Shared heading/manual resolver; checks tracked-label gate, writes parent metadata, handles unresref key migration. |

### Flow summary

1. Proof begin allocates/sets an opaque proof atom (`B-PROOF-OPAQUE-ID`).
2. If immediately after a tracked result, `\codep@proof@adjacent` stages the
   candidate and sets `\ifcodep@proof@adjcommit@needed` (`B-PROOF-ADJ`,
   `B-PROOF-DELAYED-COMMIT`).
3. The patched proof heading calls `\codep@autoproofof@scan`, which recognizes
   supported semantic ref commands and dispatches each label.
4. Same-run tracked labels resolve through `\codep@autoproofof@resolve` /
   `\codep@proofof@resolve@inner`; unresolved heading labels route through
   `\codep@autoproofof@routeforward` and later migrate from `unresref:<N>`
   (`B-PROOF-UNRESREF`).
5. On successful heading attribution, `\codep@proof@maybeheadingoverrideadjacent`
   suppresses a conflicting adjacent target before final metadata is written
   (`B-PROOF-HEADING-OVERRIDE`).
6. `\codep@bindproofparent` is the normal final write for adjacent/manual/joint
   parent links; joint headings append multiple target metadata rows to one
   proof atom (`B-PROOF-JOINT`).
7. After the heading scan, `\codep@proof@adjacent@finalize` commits only if the
   adjacent sentinel still points at the current proof's staged candidate.

### Delayed-candidate state

The delayed adjacent path stores three per-proof csnames:
`codep@adjcandidate@<proof-id>`, `codep@adjcandidate@target@<proof-id>`, and
`codep@adjcandidate@display@<proof-id>`. The persistent adjacent-target/display
csnames (`codep@proofadjtarget@<proof-id>`, `codep@proofadjdisplay@<proof-id>`)
are retained so heading override can compare target identity and print a useful
warning.

**IN-FLUX:** the sentinel-clearing trio
`\codep@proof@adjcandidate@drop`, `\codep@proof@adjacent@commit`, and
`\codep@proof@adjacent@finalize` is post-W05-C code. It may evolve when the
orphan-fallback wave lands; see `project_proof_orphan_fallback.md` before
assuming the current no-fallback semantics are final.

### Where to add a new attribution case

Start at the earliest point that has the fact you need, but keep final writes on
one rail. New heading syntax belongs in the scan/select family before
`\codep@autoproofof@dispatchlabel`; new routing for unresolved labels belongs
beside `\codep@autoproofof@routeforward`; new target-selection policy belongs
beside `\codep@proof@maybeheadingoverrideadjacent`; final parent writes should
flow through `\codep@bindproofparent` or the shared resolver so opaque identity,
prooftarget metadata, key migration, render queueing, and B-ID traceability stay
coherent.

## Anchormap rail
<deferred — see project_codemap_future_wave.md>

## Backref-rendering rail
<deferred — see project_codemap_future_wave.md>

## Pass orchestration
<deferred — see project_codemap_future_wave.md>

## Baseline ratchet
<deferred — see project_codemap_future_wave.md>

## Suppression surface
<deferred — see project_codemap_future_wave.md>

## Footer

Full CODEMAP scope is deferred to `project_codemap_future_wave.md`: complete
macro catalog for all rails, diagrams, wire-format snippets, and eventual
partial auto-generation from `@behavior` / `@implements` / `@utility` tags.
