#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPROVER=""
COMMENT=""

usage() {
    cat <<'EOF'
Usage: scripts/promote-golden.sh <run-id> <fixture-name> --approver=NAME --comment="STRING"

Promotes a run artifact to pdf-out/goldens/ as a committed visual golden.

Arguments:
  <run-id>        The timestamp prefix: <UTC>-<BRANCH>-<SHA>
  <fixture-name>  Fixture basename without .pdf (e.g., stress-ta-appendix-gray)

Required options:
  --approver=NAME     Approver identifier (name or email)
  --comment="STRING"  Approval comment (reason for promotion)

The script writes atomically: candidates are written to .tmp files first and
renamed into place only on success. A trap removes .tmp files on any failure.

After promotion, run:
  git add pdf-out/goldens/<fixture-name>.pdf pdf-out/goldens/<fixture-name>-manifest.json
  git commit -m "golden: approve <fixture-name> from run <run-id>"
EOF
    exit 0
}

if [[ $# -lt 2 ]]; then
    usage
fi

RUN_ID="$1"
FIXTURE="$2"
shift 2

for arg in "$@"; do
    case "$arg" in
        --approver=*) APPROVER="${arg#--approver=}" ;;
        --comment=*)  COMMENT="${arg#--comment=}" ;;
        --help|-h)    usage ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if [[ -z "$APPROVER" ]] || [[ -z "$COMMENT" ]]; then
    echo "error: --approver and --comment are required" >&2
    echo "Usage: $(basename "$0") <run-id> <fixture> --approver=NAME --comment=\"STRING\"" >&2
    exit 1
fi

cd "$REPO_ROOT"

SRC_PDF="pdf-out/runs/${RUN_ID}-${FIXTURE}-stress.pdf"
if [[ ! -f "$SRC_PDF" ]]; then
    echo "error: source PDF not found: ${SRC_PDF}" >&2
    echo "Available run-ids for fixture '${FIXTURE}':" >&2
    find pdf-out/runs -maxdepth 1 -name "*-${FIXTURE}-stress.pdf" -printf "  %f\n" 2>/dev/null \
        | sed "s/-${FIXTURE}-stress\.pdf//" || echo "  (none)" >&2
    exit 1
fi

GOLDEN_DIR="pdf-out/goldens"
GOLDEN_PDF="${GOLDEN_DIR}/${FIXTURE}.pdf"
GOLDEN_MANIFEST="${GOLDEN_DIR}/${FIXTURE}-manifest.json"
TMP_PDF="${GOLDEN_PDF}.tmp"
TMP_MANIFEST="${GOLDEN_MANIFEST}.tmp"

mkdir -p "${GOLDEN_DIR}"

# Trap removes .tmp files on any failure; cleared after successful atomic rename.
# shellcheck disable=SC2064
trap "rm -f '${TMP_PDF}' '${TMP_MANIFEST}'" EXIT

FIXTURE_TEX="testfiles/compiled-examples/${FIXTURE}.tex"
if [[ -f "$FIXTURE_TEX" ]]; then
    SOURCE_HASH=$(sha256sum "$FIXTURE_TEX" | awk '{print $1}')
else
    SOURCE_HASH="(source not found)"
fi

FULL_SHA=$(git rev-parse HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)

# Compute normalized comparison hash via the normalization script
NORMALIZE_SCRIPT="scripts/normalize-pdf-json.py"
if [[ -f "$NORMALIZE_SCRIPT" ]]; then
    NORM_HASH=$(nix develop --command python3 "$NORMALIZE_SCRIPT" "$SRC_PDF" \
        | sha256sum | awk '{print $1}')
else
    NORM_HASH="(normalization script not available)"
fi

# Write candidate files
cp "$SRC_PDF" "$TMP_PDF"

python3 - <<PYEOF
import json

manifest = {
    "fixture": "${FIXTURE}",
    "engine": "pdflatex",
    "branch": "${BRANCH}",
    "commit": "${FULL_SHA}",
    "timestamp": "${TIMESTAMP}",
    "run_id": "${RUN_ID}",
    "command": "nix develop --command python3 testfiles/run-tests.py --visual --filter ${FIXTURE} --keep-temp",
    "source_fixture_hash_sha256": "${SOURCE_HASH}",
    "normalized_comparison_hash_sha256": "${NORM_HASH}",
    "approver": "${APPROVER}",
    "comment": "${COMMENT}",
}
with open("${TMP_MANIFEST}", "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PYEOF

# Atomic rename: both succeed or neither does
mv "$TMP_PDF" "$GOLDEN_PDF"
mv "$TMP_MANIFEST" "$GOLDEN_MANIFEST"

# Clear the cleanup trap — success path
trap - EXIT

echo "[promote-golden] golden PDF      : ${GOLDEN_PDF}"
echo "[promote-golden] golden manifest : ${GOLDEN_MANIFEST}"
echo ""
echo "Next steps:"
echo "  git add '${GOLDEN_PDF}' '${GOLDEN_MANIFEST}'"
echo "  git commit -m \"golden: approve ${FIXTURE} from run ${RUN_ID}\""
