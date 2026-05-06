#!/usr/bin/env bash
set -u

usage() {
  printf 'Usage: %s [--sty-wave]\n' "${0##*/}" >&2
}

sty_wave=false
case "${1:-}" in
  "") ;;
  --sty-wave) sty_wave=true ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [[ $# -gt 1 ]]; then
  usage
  exit 2
fi

project_root="${PROJECT_ROOT_OVERRIDE:-}"
if [[ -z "$project_root" ]]; then
  if ! project_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    printf 'ERROR: not inside a git repository; set PROJECT_ROOT_OVERRIDE.\n' >&2
    exit 2
  fi
fi

if ! git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'ERROR: PROJECT_ROOT_OVERRIDE is not a git repository: %s\n' "$project_root" >&2
  exit 2
fi

mapfile -t staged_files < <(git -C "$project_root" diff --cached --name-only)

if [[ ${#staged_files[@]} -gt 0 ]]; then
  printf '%s\n' "${staged_files[@]}"
fi

sty_files=()
for file in "${staged_files[@]}"; do
  if [[ "$file" == *.sty ]]; then
    sty_files+=("$file")
  fi
done

if [[ ${#sty_files[@]} -eq 0 ]]; then
  exit 0
fi

sty_list="${sty_files[0]}"
for file in "${sty_files[@]:1}"; do
  sty_list+=", $file"
done
printf 'WARNING: .sty file(s) staged: %s\n' "$sty_list"
printf 'WARNING: If this commit is hygiene/scripts/docs and not a .sty wave, abort and inspect for WIP leakage.\n'

if [[ "$sty_wave" == true ]]; then
  exit 0
fi

exit 1
