# pdf-out/goldens/ — intentionally empty (golden gate dormant)

The golden-PDF comparison gate (`scripts/check-goldens.sh`) is in place but
not invoked by any build target or CI step. No goldens are committed here yet.

See `.claude/agent_memory/findings.md` entry
"Stress fixtures + golden-PDF gating: dormant until package matures (2026-05-07)"
for the three conditions that must hold before goldens are promoted and the gate
is re-enabled.

To re-enable: add a `make check-goldens` target (or equivalent nix check) that
calls `scripts/check-goldens.sh`, then use `scripts/promote-golden.sh` to
commit baseline PDFs into this directory.
