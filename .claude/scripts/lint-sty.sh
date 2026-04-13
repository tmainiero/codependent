#!/usr/bin/env bash
# lint-sty.sh — Convention enforcement for codependent .sty files.
# Runs latexindent + structural checks. Returns non-zero on violations.
# Usage: .claude/scripts/lint-sty.sh [file...]
# Default: checks codependent.sty and codependent-render.sty

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Files to check
if [ $# -gt 0 ]; then
  FILES=("$@")
else
  FILES=(codependent.sty codependent-render.sty)
fi

ERRORS=0
WARNINGS=0

err() { echo "ERROR: $1" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "WARN:  $1" >&2; WARNINGS=$((WARNINGS + 1)); }

for FILE in "${FILES[@]}"; do
  [ -f "$FILE" ] || { err "$FILE not found"; continue; }

  echo "Checking $FILE..." >&2

  # 1. latexindent formatting check (diff mode, no write)
  if command -v latexindent >/dev/null 2>&1; then
    INDENT_OUT=$(latexindent -s "$FILE" 2>/dev/null)
    if ! diff -q <(echo "$INDENT_OUT") "$FILE" >/dev/null 2>&1; then
      DIFF_LINES=$(diff <(echo "$INDENT_OUT") "$FILE" 2>/dev/null | grep -c '^[<>]' || true)
      err "$FILE: latexindent found $DIFF_LINES formatting differences. Run: latexindent -w $FILE"
    fi
  else
    warn "latexindent not on PATH — skipping format check"
  fi

  # 2. No bare \codep@tmp (must have semantic suffix like @tmp@name)
  if grep -Pn '\\codep@tmp[^@]' "$FILE" | grep -v '@tmp@' | grep -v '^\s*%' | head -5 | grep -q .; then
    err "$FILE: bare \\codep@tmp found (must use semantic suffix like \\codep@tmp@name):"
    grep -Pn '\\codep@tmp[^@]' "$FILE" | grep -v '@tmp@' | grep -v '^\s*%' | head -5 >&2
  fi

  # 3. No \errmessage or raw \message (use \PackageError/\PackageWarning/\PackageInfo)
  if grep -Pn '\\(errmessage|message)\b' "$FILE" | grep -v '^\s*%' | head -5 | grep -q .; then
    err "$FILE: raw \\errmessage or \\message found (use \\PackageError/\\PackageWarning):"
    grep -Pn '\\(errmessage|message)\b' "$FILE" | grep -v '^\s*%' | head -5 >&2
  fi

  # 4. No \usepackage inside .sty (use \RequirePackage)
  if grep -Pn '\\usepackage' "$FILE" | grep -v '^\s*%' | head -5 | grep -q .; then
    err "$FILE: \\usepackage found in .sty (use \\RequirePackage):"
    grep -Pn '\\usepackage' "$FILE" | grep -v '^\s*%' | head -5 >&2
  fi

  # 5. Line length > 100 (hard limit from CONVENTIONS.md)
  LONG_LINES=$(awk 'length > 100 && !/^\s*%/' "$FILE" | wc -l)
  if [ "$LONG_LINES" -gt 0 ]; then
    warn "$FILE: $LONG_LINES lines exceed 100 characters"
  fi

  # 6. Trailing whitespace
  TRAILING=$(grep -Pcn '\s+$' "$FILE" || true)
  if [ "$TRAILING" -gt 0 ]; then
    err "$FILE: $TRAILING lines have trailing whitespace"
  fi

  # 7. No \def for public macros (must use \newcommand/\NewDocumentCommand)
  #    Public = starts with \codep followed by lowercase (no @)
  if grep -Pn '\\def\\codep[a-z]' "$FILE" | grep -v '^\s*%' | head -5 | grep -q .; then
    err "$FILE: \\def used for public macro (use \\newcommand or \\NewDocumentCommand):"
    grep -Pn '\\def\\codep[a-z]' "$FILE" | grep -v '^\s*%' | head -5 >&2
  fi

  # 8. No \everypar or direct \par patching (use \AddToHook)
  if grep -Pn '\\everypar\b' "$FILE" | grep -v '^\s*%' | head -5 | grep -q .; then
    err "$FILE: direct \\everypar found (use \\AddToHook{para/begin}):"
    grep -Pn '\\everypar\b' "$FILE" | grep -v '^\s*%' | head -5 >&2
  fi

  # 9. All internal macros must use \codep@ prefix (catch leaked bare names)
  #    Look for \def or \newcommand of non-standard non-codep names
  #    Skip known LaTeX overrides (\newlabel, \label, etc.)
  if grep -Pn '\\(def|newcommand|renewcommand)\s*\\(?!codep|@|if|the|c@)([a-zA-Z]+)' "$FILE" | grep -v '^\s*%' | grep -v 'orig@' | head -5 | grep -q .; then
    warn "$FILE: possible non-codep@ internal macro definition:"
    grep -Pn '\\(def|newcommand|renewcommand)\s*\\(?!codep|@|if|the|c@)([a-zA-Z]+)' "$FILE" | grep -v '^\s*%' | grep -v 'orig@' | head -5 >&2
  fi

  # 10. Section headers present and in order
  SECTIONS=$(grep -n '^%% Section' "$FILE" | awk -F: '{print $2}' | sed 's/.*Section \([0-9a-z]*\).*/\1/')
  if [ -n "$SECTIONS" ]; then
    SORTED=$(echo "$SECTIONS" | sort -V)
    if [ "$SECTIONS" != "$SORTED" ]; then
      warn "$FILE: section headers may be out of order"
    fi
  fi

  # 11. Lines inside macro bodies missing % at end
  #    Heuristic: lines between \def/\newcommand and the next blank line or section header
  #    that don't end with % or { or } and aren't comments
  #    This is a best-effort check — TeX makes this hard to do perfectly
  MISSING_PCT=$(awk '
    /^\\(def|newcommand|renewcommand|NewDocumentCommand|DeclareDocumentCommand)/ { inmacro=1 }
    /^%%/ || /^$/ { inmacro=0 }
    inmacro && !/^\s*%/ && !/[%{}\\]$/ && !/^\s*$/ && !/^\\(def|newcommand|renewcommand)/ {
      count++
      if (count <= 5) print NR": "$0
    }
    END { print "TOTAL:"count+0 }
  ' "$FILE")
  MISSING_COUNT=$(echo "$MISSING_PCT" | tail -1 | cut -d: -f2)
  if [ "$MISSING_COUNT" -gt 0 ]; then
    warn "$FILE: ~$MISSING_COUNT lines in macro bodies may be missing trailing %"
    echo "$MISSING_PCT" | head -5 >&2
  fi

done

echo >&2
if [ $ERRORS -gt 0 ]; then
  echo "FAILED: $ERRORS error(s), $WARNINGS warning(s)" >&2
  exit 1
elif [ $WARNINGS -gt 0 ]; then
  echo "PASSED with $WARNINGS warning(s)" >&2
  exit 0
else
  echo "PASSED: all checks clean" >&2
  exit 0
fi
