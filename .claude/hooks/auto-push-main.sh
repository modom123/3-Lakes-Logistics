#!/usr/bin/env bash
# Auto-commit and push any pending changes to main after each Claude turn.
# Runs as a Stop hook so the repo is never more than one response behind.

set -euo pipefail

REPO="/home/user/3-Lakes-Logistics"
cd "$REPO"

# Ensure correct git author for this environment
git config user.email "noreply@anthropic.com"
git config user.name "Claude"

# Check for uncommitted changes (tracked files only — staged or unstaged)
if ! git diff --quiet || ! git diff --cached --quiet; then
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  git add -A
  git commit -m "Auto-save: $TIMESTAMP

https://claude.ai/code/session_01ApdeSEGsNkJcJfeUGRAfUH"
fi

# Push to main if local is ahead of origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")

if [ "$LOCAL" != "$REMOTE" ]; then
  git push origin HEAD:main --quiet
fi
