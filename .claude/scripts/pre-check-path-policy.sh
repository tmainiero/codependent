#!/usr/bin/env bash
# pre-check-path-policy.sh — PreToolUse advisory hook for Write/Edit.
#
# Warns (stderr, exit 0) when an agent tries to create/edit a path outside
# the Directory Map in CLAUDE.md. Non-blocking: this is education, not enforcement.
#
# Canonical allowlist lives in CLAUDE.md ("Directory Map" section). The list
# below is duplicated for fast in-hook matching — if you change one, change both.
#
# Bypass conditions:
#  - paths under /tmp/ (subagent staging area)
#  - paths under $HARNESS_TMP_ROOT/harness-staging/ if set
#  - absolute paths outside the current repo (we only police in-repo writes)

set -u

# The tool-call payload arrives via Claude Code env vars. We accept either
# $CLAUDE_FILE_PATH (PostToolUse-style) or the tool input JSON on stdin.
path="${CLAUDE_FILE_PATH:-}"
if [ -z "$path" ] && [ ! -t 0 ]; then
  # Best-effort JSON sniff without jq dependency.
  payload="$(cat || true)"
  path="$(printf '%s' "$payload" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
fi

[ -z "$path" ] && exit 0

# Bypass: ephemeral staging dirs.
case "$path" in
  /tmp/*) exit 0 ;;
  "${HARNESS_TMP_ROOT:-/__nope__}"/harness-staging/*) exit 0 ;;
esac

# Bypass: absolute paths outside the repo.
repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || pwd)"
case "$path" in
  /*)
    case "$path" in
      "$repo_root"/*) rel="${path#$repo_root/}" ;;
      *) exit 0 ;;
    esac
    ;;
  *) rel="$path" ;;
esac

# Allowlist — canonical copy in CLAUDE.md ("Directory Map").
allowed=(
  "codependent.sty"
  "codependent-render.sty"
  "docs/"
  "testfiles/"
  "scripts/"
  ".claude/"
  ".githooks/"
  "build/"
  "texbuild/"
  "pdf-out/"
  "CLAUDE.md"
  "flake.nix"
  "flake.lock"
  "shell.nix"
  "build.lua"
  ".latexmkrc"
  ".latexindent.yaml"
  ".gitignore"
  ".gitattributes"
  ".test-behavior-baseline"
  ".traceability-baseline"
)

for prefix in "${allowed[@]}"; do
  case "$prefix" in
    */) case "$rel" in "$prefix"*) exit 0 ;; esac ;;
    *)  [ "$rel" = "$prefix" ] && exit 0 ;;
  esac
done

# Suggest closest allowed prefix (first-token match).
top="${rel%%/*}"
suggest=""
for prefix in "${allowed[@]}"; do
  case "$prefix" in
    "$top"*|"${top}"/*) suggest="$prefix"; break ;;
  esac
done
[ -z "$suggest" ] && suggest="docs/ or testfiles/ (see CLAUDE.md Directory Map)"

cat >&2 <<EOF
PATH-POLICY ADVISORY: $rel is not in the Directory Map in CLAUDE.md.
If this is intentional, update the Directory Map first. If a typo/mistake,
the right path is probably $suggest.
EOF

exit 0
