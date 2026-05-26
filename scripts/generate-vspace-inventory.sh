#!/usr/bin/env bash
# generate-vspace-inventory.sh -- Adjacency-aware VSPACE transition emitter.
#
# Scans .lvt fixtures for adjacent end{env}/begin{env} pairs (with optional
# intervening blank/comment lines) and emits a machine-readable JSON inventory
# of every env→env transition.
#
# Usage:
#   scripts/generate-vspace-inventory.sh [--output PATH]
#
# Options:
#   --output PATH   Path to write the JSON inventory (default: testfiles/output/vspace-inventory.json)
#
# Output schema (JSON array of transition objects):
#   {
#     "fixture": "testfiles/unit/foo.lvt",   -- relative path from repo root
#     "from_env": "theorem",                  -- env name after \end{
#     "to_env": "proof",                      -- env name after \begin{
#     "line_span": [N, M]                     -- 1-based line range [end-line, begin-line]
#   }
#
# The generated inventory is gitignored (testfiles/output/vspace-inventory.json).
# The committed classification lives at testfiles/vspace-inventory-manifest.json.
# Run validate-vspace-manifest.py AFTER this script to cross-check manifest entries.
#
# Exit codes:
#   0 -- success
#   1 -- error (bad args, write failure)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_PATH="$REPO_ROOT/testfiles/output/vspace-inventory.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --output=*)
      OUTPUT_PATH="${1#--output=}"
      shift
      ;;
    *)
      echo "generate-vspace-inventory.sh: unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Ensure output directory exists.
mkdir -p "$(dirname "$OUTPUT_PATH")"

# Collect .lvt fixtures from unit/ and integration/
mapfile -t FIXTURES < <(
  find "$REPO_ROOT/testfiles/unit" "$REPO_ROOT/testfiles/integration" \
       -name "*.lvt" -type f | sort
)

# Python inline parser: tolerates leading whitespace, emits JSON.
python3 - "$REPO_ROOT" "$OUTPUT_PATH" "${FIXTURES[@]}" <<'PYEOF'
import sys
import json
import re
import os

repo_root = sys.argv[1]
output_path = sys.argv[2]
fixture_paths = sys.argv[3:]

# Regex patterns (tolerates leading whitespace)
RE_END   = re.compile(r'^\s*\\end\{([^}]+)\}')
RE_BEGIN = re.compile(r'^\s*\\begin\{([^}]+)\}')
RE_BLANK_OR_COMMENT = re.compile(r'^\s*(%.*)?$')

transitions = []

for fpath in fixture_paths:
    rel = os.path.relpath(fpath, repo_root)
    try:
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        continue

    i = 0
    while i < len(lines):
        m_end = RE_END.match(lines[i])
        if m_end:
            from_env = m_end.group(1)
            end_lineno = i + 1  # 1-based
            j = i + 1
            # Skip blank/comment lines
            while j < len(lines) and RE_BLANK_OR_COMMENT.match(lines[j]):
                j += 1
            if j < len(lines):
                m_begin = RE_BEGIN.match(lines[j])
                if m_begin:
                    to_env = m_begin.group(1)
                    begin_lineno = j + 1  # 1-based
                    transitions.append({
                        "fixture": rel.replace(os.sep, '/'),
                        "from_env": from_env,
                        "to_env": to_env,
                        "line_span": [end_lineno, begin_lineno],
                    })
        i += 1

with open(output_path, 'w', encoding='utf-8') as out:
    json.dump(transitions, out, indent=2)
    out.write('\n')

print(f"generate-vspace-inventory: wrote {len(transitions)} transition(s) to {output_path}")
PYEOF
