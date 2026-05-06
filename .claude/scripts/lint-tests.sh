#!/usr/bin/env bash
# lint-tests.sh — Convention enforcement for .lvt test files.
# Checks assertion minimums, negative assertion requirements, format.
# Usage: .claude/scripts/lint-tests.sh [file...]
# Default: checks all .lvt files in testfiles/unit/ and testfiles/integration/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Files to check
if [ $# -gt 0 ]; then
  FILES=("$@")
else
  FILES=()
  for f in testfiles/unit/*.lvt testfiles/integration/*.lvt; do
    [ -f "$f" ] && FILES+=("$f")
  done
fi

ERRORS=0
WARNINGS=0

err() { echo "ERROR: $1" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "WARN:  $1" >&2; WARNINGS=$((WARNINGS + 1)); }

for FILE in "${FILES[@]}"; do
  [ -f "$FILE" ] || { err "$FILE not found"; continue; }
  NAME=$(basename "$FILE" .lvt)

  # 1. Must have TEST-NAME header
  if ! grep -q '^%% TEST-NAME:' "$FILE"; then
    err "$FILE: missing TEST-NAME header"
  fi

  # 2. Must have TEST-WHAT header
  if ! grep -q '^%% TEST-WHAT:' "$FILE"; then
    err "$FILE: missing TEST-WHAT header"
  fi

  # 3. Must have TEST-EXIT header
  if ! grep -q '^%% TEST-EXIT:' "$FILE"; then
    err "$FILE: missing TEST-EXIT header"
  fi

  # 4. Minimum 4 assertions (excluding metadata headers)
  # Includes the four W03-P01-A1 directive families:
  #   EXPECT-PACKAGE-WARNING, EXPECT-PACKAGE-ERROR,
  #   PDF-APPENDIX-ENTRY, PDF-APPENDIX-ENTRY-TEXT-ONLY
  ASSERT_COUNT=$(grep -cP '^%% TEST-(EXIT|LOG-NOT|LOG-CONTAINS|CDP-CONTAINS|CDP-NOT-CONTAINS|CDP-COUNT|CDP-LAST-RECORD|AUX-CONTAINS|AUX-NOT-CONTAINS|ATOMS-MIN|PDF-CONTAINS|PDF-NOT|PDF-LINKS|PDF-STEXT|PDF-STEXT-NOT|PDF-OBJECTS|PDF-OBJECTS-NOT|PDF-LINK-DEST|PDF-LINK-DEST-NOT|PDF-LINK-COUNT|PDF-DEST-EXISTS|PDF-DEST-NOT-EXISTS|PDF-LINK-RECT|PDF-NO-ORPHAN-LINKS|PDF-ALL-BACKREFS-LINKED|PDF-BACKREF-TARGETS|EXPECT-PACKAGE-WARNING|EXPECT-PACKAGE-ERROR|PDF-APPENDIX-ENTRY|PDF-APPENDIX-ENTRY-TEXT-ONLY):' "$FILE" || true)
  if [ "$ASSERT_COUNT" -lt 4 ]; then
    err "$FILE: only $ASSERT_COUNT assertions (minimum 4)"
  fi

  # 5. Must have at least 1 negative assertion
  NEG_COUNT=$(grep -cP '^%% TEST-(LOG-NOT|CDP-NOT-CONTAINS|AUX-NOT-CONTAINS|PDF-NOT|PDF-STEXT-NOT|PDF-OBJECTS-NOT|PDF-LINK-DEST-NOT|PDF-DEST-NOT-EXISTS):' "$FILE" || true)
  if [ "$NEG_COUNT" -lt 1 ]; then
    warn "$FILE: no negative assertions (should have >= 1 TEST-*-NOT-*)"
  fi

  # 6. Must have \START and \END markers
  if ! grep -q '\\START' "$FILE"; then
    warn "$FILE: missing \\START marker"
  fi
  if ! grep -q '\\END' "$FILE"; then
    warn "$FILE: missing \\END marker"
  fi

  # 7. Must have TEST-RERUN header
  if ! grep -q '^%% TEST-RERUN:' "$FILE"; then
    warn "$FILE: missing TEST-RERUN header"
  fi

  # 8. Must have TEST-PACKAGES header
  if ! grep -q '^%% TEST-PACKAGES:' "$FILE"; then
    warn "$FILE: missing TEST-PACKAGES header"
  fi

  # 9. ALL-BACKREFS-LINKED requires at least one BACKREF-TARGETS (link correctness)
  if grep -q '^%% TEST-PDF-ALL-BACKREFS-LINKED:' "$FILE"; then
    TARGETS_COUNT=$(grep -cP '^%% TEST-PDF-BACKREF-TARGETS:' "$FILE" || true)
    if [ "$TARGETS_COUNT" -lt 1 ]; then
      warn "$FILE: has ALL-BACKREFS-LINKED but no BACKREF-TARGETS (link correctness unchecked)"
    fi
  fi

  # 10. Rerun-header rule: if TEST-PASS-COUNT-* is declared, TEST-RERUN must
  #     be present (multi-pass fixtures require an explicit pass count header).
  #     P01(B) registers the PASS-COUNT-* directives in the runner; this linter
  #     rule is self-contained and works by string-pattern recognition.
  if grep -qP '^%% TEST-PASS-COUNT-(COLD|WARM|WARM-CHANGED):' "$FILE"; then
    if ! grep -q '^%% TEST-RERUN:' "$FILE"; then
      err "$FILE: declares TEST-PASS-COUNT-* but missing TEST-RERUN header"
    fi
  fi

  # 11. Any TEST-ALLOW-UNDEFINED-REFS: yes waiver must have a nearby
  # documented rationale comment within 3 lines (before or after).
  while IFS=: read -r LINE_NO _; do
    [ -n "$LINE_NO" ] || continue
    START=$(( LINE_NO > 3 ? LINE_NO - 3 : 1 ))
    END=$(( LINE_NO + 3 ))
    WINDOW=$(sed -n "${START},${END}p" "$FILE")
    if ! printf '%s\n' "$WINDOW" | grep -qP '^%%(?!\s*TEST-).+'; then
      err "$FILE:$LINE_NO: TEST-ALLOW-UNDEFINED-REFS: yes requires a nearby %% rationale comment within 3 lines"
    fi
  done < <(grep -n '^%% TEST-ALLOW-UNDEFINED-REFS: yes$' "$FILE" || true)

done

# Run drift linter: no legacy sbl symbols in active code.
if ! python3 .claude/scripts/lint_no_sbl.py; then
  ERRORS=$((ERRORS + 1))
fi

echo >&2
if [ $ERRORS -gt 0 ]; then
  echo "FAILED: $ERRORS error(s), $WARNINGS warning(s) across ${#FILES[@]} files" >&2
  exit 1
elif [ $WARNINGS -gt 0 ]; then
  echo "PASSED with $WARNINGS warning(s) across ${#FILES[@]} files" >&2
  exit 0
else
  echo "PASSED: all ${#FILES[@]} files clean" >&2
  exit 0
fi
