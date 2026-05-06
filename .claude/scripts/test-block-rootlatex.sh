#!/usr/bin/env bash
# test-block-rootlatex.sh — Unit tests for .claude/scripts/block-rootlatex.sh
#
# Run with: bash .claude/scripts/test-block-rootlatex.sh
# TODO: wire into lint-tests.sh once harness hygiene suite is formalised.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/.claude/scripts/block-rootlatex.sh"

if [ ! -x "$HOOK" ]; then
  echo "FATAL: hook not found or not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0

# run_case <description> <command-string> <expected-exit>
#   expected-exit: 0 = allow, 2 = block
run_case() {
  local desc="$1"
  local cmd="$2"
  local expected="$3"

  local payload
  payload=$(jq -n --arg cmd "$cmd" '{tool_name:"Bash",tool_input:{command:$cmd}}')

  local actual
  actual=0
  printf '%s' "$payload" | bash "$HOOK" >/dev/null 2>&1 || actual=$?

  if [ "$actual" -eq "$expected" ]; then
    PASS=$(( PASS + 1 ))
    printf 'PASS  [%s]\n' "$desc"
  else
    FAIL=$(( FAIL + 1 ))
    printf 'FAIL  [%s]  expected exit %d, got %d\n' "$desc" "$expected" "$actual" >&2
    printf '      cmd: %s\n' "$cmd" >&2
  fi
}

# ---------------------------------------------------------------------------
# ALLOW cases (exit 0)
# ---------------------------------------------------------------------------

run_case \
  "git commit with pdflatex in message (engine token in commit message)" \
  'git commit -m "fix pdflatex invocation"' \
  0

run_case \
  "echo with pdflatex in string (engine token in echo string)" \
  'echo "pdflatex is the engine"' \
  0

run_case \
  "grep for pdflatex pattern (engine token in grep pattern)" \
  'grep "pdflatex" file.txt' \
  0

run_case \
  "latexmk -pdf (latexmk reads .latexmkrc)" \
  'latexmk -pdf foo.tex' \
  0

run_case \
  "pdflatex with -output-directory (explicit output dir)" \
  'pdflatex -output-directory=texbuild foo.tex' \
  0

run_case \
  "pdflatex with -output-directory space-separated" \
  'pdflatex -output-directory texbuild foo.tex' \
  0

run_case \
  "pdflatex with -aux-directory" \
  'pdflatex -aux-directory=texbuild foo.tex' \
  0

run_case \
  "python3 test runner (no engine token at all)" \
  'python3 testfiles/run-tests.py' \
  0

run_case \
  "latexmk in pipeline with && (latexmk prefix)" \
  'latexmk foo.tex && echo done' \
  0

run_case \
  "xelatex with -output-directory (explicit out dir)" \
  'xelatex -output-directory=texbuild foo.tex' \
  0

run_case \
  "lualatex with -output-directory (explicit out dir)" \
  'lualatex -output-directory=texbuild foo.tex' \
  0

# Note: 'cd texbuild && pdflatex foo.tex' is NOT allowed by the hook.
# The hook detects the pdflatex invocation after &&, and neither latexmk
# nor -output-directory is present, so it blocks. This matches the hook
# contract: the hook does not track cwd changes.

# ---------------------------------------------------------------------------
# BLOCK cases (exit 2)
# ---------------------------------------------------------------------------

run_case \
  "bare pdflatex invocation (pdflatex foo.tex)" \
  'pdflatex foo.tex' \
  2

run_case \
  "pdflatex with --shell-escape flag" \
  'pdflatex --shell-escape foo.tex' \
  2

run_case \
  "xelatex bare invocation" \
  'xelatex foo.tex' \
  2

run_case \
  "lualatex bare invocation" \
  'lualatex foo.tex' \
  2

run_case \
  "cd texbuild && pdflatex foo.tex (hook does not track cwd)" \
  'cd texbuild && pdflatex foo.tex' \
  2

run_case \
  "latex bare invocation" \
  'latex foo.tex' \
  2

run_case \
  "pdflatex in subshell: \$(pdflatex foo.tex)" \
  '$(pdflatex foo.tex)' \
  2

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$(( PASS + FAIL ))
printf '\nPASS: %d  FAIL: %d  (of %d)\n' "$PASS" "$FAIL" "$TOTAL"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
