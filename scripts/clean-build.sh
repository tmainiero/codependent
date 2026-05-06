#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
PURGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --purge) PURGE=1; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Directories to organize
TEXBUILD_DIR="texbuild"
PDF_OUT_DIR="pdf-out"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")

# Extensions to organize
TEXBUILD_EXTS=(aux log fls fdb_latexmk out cdp toc synctex.gz nav snm bbl blg idx ind ilg)
PDF_EXTS=(pdf)

# Directories to search
SEARCH_DIRS=("$REPO_ROOT" "$REPO_ROOT/testfiles" "$REPO_ROOT/testfiles/compiled-examples")

# Directories to exclude from search
EXCLUDE_DIRS=("$REPO_ROOT/texbuild" "$REPO_ROOT/pdf-out" "$REPO_ROOT/build" "$REPO_ROOT/.git" "$REPO_ROOT/.claude" "$REPO_ROOT/testfiles/output" "$REPO_ROOT/testfiles/tmp")

# Function to check if a path is in excluded dirs
is_excluded() {
  local path="$1"
  for exclude in "${EXCLUDE_DIRS[@]}"; do
    if [[ "$path" == "$exclude"* ]]; then
      return 0
    fi
  done
  return 1
}

# Function to check if a file is tracked in git (skip tracked files)
is_tracked() {
  git ls-files --error-unmatch "$1" >/dev/null 2>&1
}

texbuild_count=0
pdf_count=0

# Process texbuild extensions
for ext in "${TEXBUILD_EXTS[@]}"; do
  while IFS= read -r file; do
    if is_excluded "$file"; then
      continue
    fi
    if is_tracked "$file"; then
      continue
    fi
    if [[ -f "$file" ]]; then
      if [[ $PURGE -eq 1 ]]; then
        if [[ $DRY_RUN -eq 0 ]]; then
          rm "$file"
        fi
        ((texbuild_count++)) || true
      else
        if [[ $DRY_RUN -eq 0 ]]; then
          mkdir -p "$TEXBUILD_DIR"
          mv "$file" "$TEXBUILD_DIR/"
        fi
        ((texbuild_count++)) || true
      fi
    fi
  done < <(find "${SEARCH_DIRS[@]}" -maxdepth 1 -name "*.$ext" 2>/dev/null || true)
done

# Process PDF extensions
for ext in "${PDF_EXTS[@]}"; do
  while IFS= read -r file; do
    if is_excluded "$file"; then
      continue
    fi
    if is_tracked "$file"; then
      continue
    fi
    if [[ -f "$file" ]]; then
      if [[ $PURGE -eq 1 ]]; then
        if [[ $DRY_RUN -eq 0 ]]; then
          rm "$file"
        fi
        ((pdf_count++)) || true
      else
        if [[ $DRY_RUN -eq 0 ]]; then
          mkdir -p "$PDF_OUT_DIR"
          mv "$file" "$PDF_OUT_DIR/"
        fi
        ((pdf_count++)) || true
      fi
    fi
  done < <(find "${SEARCH_DIRS[@]}" -maxdepth 1 -name "*.$ext" 2>/dev/null || true)
done

# Print summary
if [[ $texbuild_count -eq 0 && $pdf_count -eq 0 ]]; then
  echo "clean"
else
  if [[ $PURGE -eq 1 ]]; then
    echo "purged $texbuild_count files from texbuild, $pdf_count files from pdf-out"
  else
    echo "moved $texbuild_count files to texbuild/, $pdf_count files to pdf-out/"
  fi
fi

exit 0
