#!/usr/bin/env bash
# Run this yourself to publish the verified source changes; no raw logs are staged.
set -euo pipefail

PUBLISH_SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PUBLISH_STAMP=$(date -u +%Y%m%d-%H%M%S)
PUBLISH_TARGET="$(dirname "$PUBLISH_SOURCE")/drone_forensics_update_$PUBLISH_STAMP"
PUBLISH_BRANCH="publish-verified-updates-$PUBLISH_STAMP"
PUBLISH_FILES=(
  README.md requirements.txt requirements-dev.txt
  acquisition/acquire.py cli/main.py cli/pipeline.py
  platform_parsers/mavlink/tlog_parser.py
  media/extractor.py reporting/evidence_gallery.py
  tests/test_cli_process.py
  tools/process_pixhawk6c_mini_logs.py
  tools/add_pixhawk6c_mini_ml_reports.py
  tools/publish_verified_updates.sh
  RECENT_CHANGES.md PUBLISHING_CHECKLIST.md
  GITHUB_CHANGES_ONE_LINE_EACH.txt
  reports/readme-serial-verification.json
)

for PUBLISH_FILE in "${PUBLISH_FILES[@]}"; do
  if [[ ! -f "$PUBLISH_SOURCE/$PUBLISH_FILE" ]]; then
    printf 'Missing required file: %s\n' "$PUBLISH_SOURCE/$PUBLISH_FILE" >&2
    exit 1
  fi
done

python3 - "$PUBLISH_SOURCE" <<'PY'
from pathlib import Path
import hashlib, json, sys
root = Path(sys.argv[1])
receipt = json.loads((root / 'reports/readme-serial-verification.json').read_text())
if receipt.get('candidate_workflow_status') != 'passed':
    raise SystemExit('The serial README workflow has not passed verification.')
for relative, expected in receipt['tested_source_sha256'].items():
    actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f'Verified source changed after testing: {relative}')
print('Verified source hashes match the passing README workflow.')
PY

if [[ "${1:-}" == "--dry-run" ]]; then
  printf 'Source: %s\nTarget: %s\nBranch: %s\n' "$PUBLISH_SOURCE" "$PUBLISH_TARGET" "$PUBLISH_BRANCH"
  printf '%s\n' "${PUBLISH_FILES[@]}"
  exit 0
fi
if [[ $# -ne 0 ]]; then
  printf 'Usage: bash tools/publish_verified_updates.sh [--dry-run]\n' >&2
  exit 2
fi

git -C "$PUBLISH_SOURCE" fetch origin main
GIT_LFS_SKIP_SMUDGE=1 git -C "$PUBLISH_SOURCE" worktree add \
  -b "$PUBLISH_BRANCH" "$PUBLISH_TARGET" origin/main
for PUBLISH_FILE in "${PUBLISH_FILES[@]}"; do
  mkdir -p "$PUBLISH_TARGET/$(dirname "$PUBLISH_FILE")"
  cp "$PUBLISH_SOURCE/$PUBLISH_FILE" "$PUBLISH_TARGET/$PUBLISH_FILE"
done

git -C "$PUBLISH_TARGET" add -- "${PUBLISH_FILES[@]}"
if git -C "$PUBLISH_TARGET" diff --cached --quiet; then
  printf 'The selected updates are already on origin/main.\n'
  exit 0
fi
git -C "$PUBLISH_TARGET" diff --cached --stat
git -C "$PUBLISH_TARGET" commit -m "Wire forensic pipeline and verify README workflow"
git -C "$PUBLISH_TARGET" push origin HEAD:main
printf 'Published source and verification updates from %s\n' "$PUBLISH_TARGET"
