#!/usr/bin/env bash
# PreToolUse Bash hook: run full traceability lint before relevant commits.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))' 2>/dev/null)

[ -z "$CMD" ] && exit 0

if ! printf '%s' "$CMD" | grep -qE '^[[:space:]]*git[[:space:]]+commit([[:space:]]|$)'; then
  exit 0
fi

STAGED=$(git diff --cached --name-only -- \
  codependent.sty \
  codependent-render.sty \
  docs/BEHAVIOR.md \
  ':(glob)testfiles/unit/*.lvt' \
  ':(glob)testfiles/integration/*.lvt')

[ -z "$STAGED" ] && exit 0

python3 .claude/scripts/lint_traceability.py
