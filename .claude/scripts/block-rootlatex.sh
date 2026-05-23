#!/usr/bin/env bash
# PreToolUse Bash hook: block raw LaTeX compiles that would pollute the repo root.
# Allows: latexmk (reads .latexmkrc), or any latex/pdflatex/lualatex/xelatex call
# with -output-directory= set. Blocks everything else that invokes a TeX engine.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))' 2>/dev/null)

[ -z "$CMD" ] && exit 0

# Match an actual engine invocation: command-start prefix + engine word + an
# argument that looks like a flag or .tex file. This filters out bare tokens
# inside commit messages, echo strings, or doc text.
if printf '%s' "$CMD" | grep -qE '(^|[;&|`( ])(pdflatex|lualatex|xelatex|latex)[[:space:]]+(-[^[:space:]]+|[^[:space:]]+\.tex)'; then
  # latexmk is the blessed entrypoint (reads .latexmkrc → texbuild/, pdf-out/).
  if printf '%s' "$CMD" | grep -qE '(^|[;&|`( ])latexmk( |$)'; then
    exit 0
  fi
  # Allow if -output-directory or -aux-directory is set explicitly.
  if printf '%s' "$CMD" | grep -qE -- '-(output|aux)-directory[ =]'; then
    exit 0
  fi
  cat >&2 <<'EOF'
[block-rootlatex] Raw TeX compile would litter the repo root with .aux/.log/.pdf.

Use ONE of:
  latexmk <file>.tex                              # reads .latexmkrc (preferred)
  pdflatex -output-directory=texbuild <file>.tex  # explicit out-dir
  nix develop --command python3 scripts/run-tests.py [--filter X]   # test suite

If you must compile a one-off, write the .tex under testfiles/ or /tmp/, never the repo root.
EOF
  exit 2
fi

exit 0
