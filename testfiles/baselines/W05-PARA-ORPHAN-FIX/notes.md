# W05-PARA-ORPHAN-FIX baseline notes

Captured at wave rotation P05 (commit following `342088a`).

## Pre-existing drift absorbed at rotation

Three fixture entries in this manifest carry hash changes that are **not** caused by
W05-PARA-ORPHAN-FIX. They are carry-over drift from **W05-PRINTKIND-DISPLAY-OVERRIDE**
(commit `eaf0ce9`) that was present in the source baseline
(`testfiles/baselines/W05-PRINTKIND-DISPLAY-NAME/`) but never rotated into that baseline.
The delta-investigation at `.claude/comms/waves/W05-PARA-ORPHAN-FIX/delta-investigation.md`
confirmed this by comparing pre-fix `68daade` vs post-fix HEAD and finding byte-identical
outputs for these three fixtures.

| Fixture | Fields | Root cause |
|---|---|---|
| `trinity-test` | `aux_sha`, `cdp_sha` | `tadec` appendix-display override stress atom added at `testfiles/integration/trinity-test.lvt:343-350` and `:733-743` in `eaf0ce9` |
| `integ-tcolorbox-appendix-name-link-plain` | `cdp_sha` | Source-line offset shifts at `.lvt:2-8`, `:33` in `eaf0ce9` |
| `integ-keytheorems-heading-custom-name-link` | `cdp_sha` | Source-line offset shifts at `.lvt:2-6`, `:31`, `:46` in `eaf0ce9` |

These are **expected** and **benign** — they reflect legitimate fixture edits that were
already committed before this wave. They are not orphan-paragraph fix effects.

## New fixtures added at this rotation

Five fixtures were added by W05-PARA-ORPHAN-FIX and appear here for the first time:

- `integ-no-orphan-para-after-tracked-env` — P02, amsthm + thmtools teardown
- `integ-keytheorems-para-teardown-no-orphan` — P04, keytheorems backend
- `integ-tcolorbox-para-teardown-no-orphan` — P04, tcolorbox backend
- `integ-thmtools-para-teardown-no-orphan` — P04, thmtools backend (has live nested-close block)
- `integ-ntheorem-para-teardown-no-orphan` — P04, ntheorem backend
