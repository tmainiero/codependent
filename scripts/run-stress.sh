#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP_GENERATIONS=15
PRUNE_ARCHIVE=false
DRY_RUN=false
FILTER=""

usage() {
    cat <<'EOF'
Usage: scripts/run-stress.sh [OPTIONS]

Thin wrapper over run-tests.py --visual. Compiles stress fixtures through the
runner (preserving TEST-PDF assertion machinery) and archives each run under
pdf-out/runs/ with a flat naming scheme.

Options:
  --filter REGEX         Forward to run-tests.py --filter (fixture name pattern)
  --keep-generations N   Keep N newest run generations when pruning (default: 15)
  --prune-archive        Move older generations to pdf-out/runs/archive/
  --dry-run              Print planned actions without writing files or running tests
  --help                 Show this message

Artifacts produced per run:
  pdf-out/runs/<UTC>-<BRANCH>-<SHA>-<fixture>-stress.pdf
  pdf-out/runs/<UTC>-<BRANCH>-<SHA>-manifest.json

A "generation" is one execution identified by its <UTC>-<BRANCH>-<SHA> prefix.
--prune-archive keeps the newest N generations; older ones move to archive/.
archive/ is never silently purged.

To promote a run's output to committed goldens:
  scripts/promote-golden.sh <run-id> <fixture> --approver=NAME --comment="..."
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --filter) FILTER="$2"; shift 2 ;;
        --keep-generations) KEEP_GENERATIONS="$2"; shift 2 ;;
        --prune-archive) PRUNE_ARCHIVE=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

UTC=$(date -u +%Y%m%dT%H%M%SZ)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
SHA=$(git rev-parse --short HEAD)
RUN_ID="${UTC}-${BRANCH}-${SHA}"

RUNS_DIR="pdf-out/runs"
MANIFEST_FILE="${RUNS_DIR}/${RUN_ID}-manifest.json"

RUNNER_ARGS="--visual --keep-temp"
if [[ -n "$FILTER" ]]; then
    RUNNER_ARGS="${RUNNER_ARGS} --filter ${FILTER}"
fi

if $DRY_RUN; then
    echo "[run-stress] DRY RUN — no files written"
    echo "[run-stress] run-id    : ${RUN_ID}"
    echo "[run-stress] command   : nix develop --command python3 scripts/run-tests.py ${RUNNER_ARGS}"
    echo "[run-stress] artifacts : ${RUNS_DIR}/${RUN_ID}-<fixture>-stress.pdf"
    echo "[run-stress] manifest  : ${MANIFEST_FILE}"
    if $PRUNE_ARCHIVE; then
        echo "[run-stress] prune     : keep ${KEEP_GENERATIONS} newest; move older to ${RUNS_DIR}/archive/"
    fi
    exit 0
fi

mkdir -p "${RUNS_DIR}"

echo "[run-stress] run-id  : ${RUN_ID}"
echo "[run-stress] command : nix develop --command python3 scripts/run-tests.py ${RUNNER_ARGS}"

RUNNER_EXIT=0
# shellcheck disable=SC2086
nix develop --command python3 scripts/run-tests.py ${RUNNER_ARGS} || RUNNER_EXIT=$?

# Discover stress PDFs produced by this run.
# With a filter, scan pdf-out/ for files whose basename matches the filter pattern.
# Without a filter, collect all stress-*.pdf.
ARTIFACTS=()
if [[ -n "$FILTER" ]]; then
    while IFS= read -r -d '' f; do
        base=$(basename "$f" .pdf)
        if [[ "$base" =~ $FILTER ]]; then
            ARTIFACTS+=("$f")
        fi
    done < <(find pdf-out -maxdepth 1 -name "*.pdf" -print0 2>/dev/null)
else
    while IFS= read -r -d '' f; do
        ARTIFACTS+=("$f")
    done < <(find pdf-out -maxdepth 1 -name "stress-*.pdf" -print0 2>/dev/null)
fi

ARCHIVED=()
for SRC in "${ARTIFACTS[@]+"${ARTIFACTS[@]}"}"; do
    FIXTURE=$(basename "$SRC" .pdf)
    DEST="${RUNS_DIR}/${RUN_ID}-${FIXTURE}-stress.pdf"
    cp "$SRC" "$DEST"
    ARCHIVED+=("$DEST")
    echo "[run-stress] archived : ${DEST}"
done

# Write per-run manifest via Python (avoids fragile JSON quoting in shell)
python3 - "${ARCHIVED[@]+"${ARCHIVED[@]}"}" <<PYEOF
import json, sys

artifacts = sys.argv[1:]
manifest = {
    "run_id": "${RUN_ID}",
    "timestamp": "${UTC}",
    "branch": "${BRANCH}",
    "sha": "${SHA}",
    "command": "nix develop --command python3 scripts/run-tests.py ${RUNNER_ARGS}",
    "artifacts": artifacts,
    "runner_exit_code": ${RUNNER_EXIT},
}
with open("${MANIFEST_FILE}", "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
print(f"[run-stress] manifest : ${MANIFEST_FILE}")
PYEOF

if $PRUNE_ARCHIVE; then
    python3 - "${RUNS_DIR}" "${KEEP_GENERATIONS}" <<'PYEOF'
import os, re, shutil, sys

runs_dir, keep_str = sys.argv[1], sys.argv[2]
keep = int(keep_str)
archive_dir = os.path.join(runs_dir, "archive")

manifest_re = re.compile(r'^(\d{8}T\d{6}Z-[^-]+-[0-9a-f]+-manifest\.json)$')
manifests = sorted(
    [f for f in os.listdir(runs_dir) if manifest_re.match(f)],
    reverse=True,
)

to_archive = manifests[keep:]
if not to_archive:
    print(f"[run-stress] prune: {len(manifests)} generation(s), nothing to archive (keep={keep})")
else:
    os.makedirs(archive_dir, exist_ok=True)
    for mf in to_archive:
        gen_prefix = mf.replace("-manifest.json", "")
        for fname in sorted(os.listdir(runs_dir)):
            if fname.startswith(gen_prefix) and os.path.isfile(os.path.join(runs_dir, fname)):
                src = os.path.join(runs_dir, fname)
                dst = os.path.join(archive_dir, fname)
                shutil.move(src, dst)
                print(f"[run-stress] -> archive/: {fname}")
    print(f"[run-stress] prune: kept {min(keep, len(manifests))}, moved {len(to_archive)} generation(s) to archive/")
PYEOF
fi

exit "${RUNNER_EXIT}"
