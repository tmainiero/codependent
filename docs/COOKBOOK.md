# codependent cookbook

Recipes for placing `\codepbackrefs` in custom theorem styles and
related rendering workflows.

*This stub lands with the v2.0 deletion of `backref-style=below|margin`.
Enrichment (full recipe set) lands in a follow-up release.  See the
pointer from the `\codepsetup{backref-style=below}` and
`\codepsetup{backref-style=margin}` migration errors — those keys no
longer produce a rendering path; callers must invoke `\codepbackrefs`
from a custom endmark instead.*

## Migration (v2.0)

**Old (pre-v2.0)**:
```latex
\codepsetup{backref-style=below}
```
emitted the "Used in ..." block on a separate line after the theorem
env closed.

**New**: place `\codepbackrefs` in the theorem's `\newtheoremstyle`
endmark (or anywhere inside the tracked env body):

```latex
\newtheoremstyle{codep-used}%
  {}{}%
  {\itshape}{}%
  {\bfseries}{.}%
  { }%
  {\thmname{#1}\thmnumber{ #2}\thmnote{ (#3)}\codepbackrefs}
\theoremstyle{codep-used}
\newtheorem{theorem}{Theorem}
\codeptrack{theorem}
```

After `\codepbackrefs` fires inside a tracked atom, auto-flush is
suppressed for that atom — the manual call replaces the auto call.

## Recipes (stubs; enrichment deferred to P07)

- Endmark placement in `amsthm` `\newtheoremstyle`.
- Endmark placement in `thmtools` `\declaretheoremstyle`.
- Margin placement via a custom `\marginpar` wrapper around
  `\codepbackrefs`.
- Paragraph-atom usage: call `\codepbackrefs` inside the paragraph
  body to emit at a specific point (default: no auto-emission).
- Interaction with `\restatable` / `thmtools` restate: replay fires
  are automatically suppressed.
