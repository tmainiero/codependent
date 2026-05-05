#!/usr/bin/env bash
# check-investigator-output.sh — pre-dispatch gate for waves that require an
# investigator report to exist before a coder agent can be dispatched.
#
# Usage: scripts/check-investigator-output.sh <investigator-output-path> [<receipt-json-path>]
#
# Exits 0 with one-line "OK <path>" on stdout when:
#   - the investigator output file exists and is non-empty
#   - if a receipt JSON is given, it parses and contains "status": "pass"
#
# Exits 1 with one-line "FAIL <reason>" on stdout otherwise. (Failure messages
# go to stdout, not stderr, so callers can capture both with one redirect.)
# Exits 2 with usage on stderr if argument count is wrong.
#
# Not a PreToolUse hook. Orchestrator-discipline gate — the orchestrator runs
# this between an investigator agent and the dependent coder agent.

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <investigator-output-path> [<receipt-json-path>]" >&2
  exit 2
fi

out="$1"
receipt="${2:-}"

if [[ ! -f "$out" ]]; then
  echo "FAIL missing investigator output: $out"
  exit 1
fi

if [[ ! -s "$out" ]]; then
  echo "FAIL empty investigator output: $out"
  exit 1
fi

if [[ -n "$receipt" ]]; then
  if [[ ! -f "$receipt" ]]; then
    echo "FAIL missing receipt: $receipt"
    exit 1
  fi
  if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('status')=='pass' else 1)" "$receipt"; then
    echo "FAIL receipt status not pass: $receipt"
    exit 1
  fi
fi

echo "OK $out"
exit 0
