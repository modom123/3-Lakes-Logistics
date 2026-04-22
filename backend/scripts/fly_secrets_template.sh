#!/usr/bin/env bash
# Push every secret from .env to Fly in one call.
# Usage:
#   cp .env.example .env.prod && edit .env.prod
#   ./scripts/fly_secrets_template.sh .env.prod
#
# Only keys NOT already in fly.toml [env] are forwarded.

set -euo pipefail

ENVFILE="${1:-.env.prod}"
[ -f "$ENVFILE" ] || { echo "env file $ENVFILE not found"; exit 1; }

# Keys that are already set non-sensitively in fly.toml — skip them.
NON_SECRET_KEYS="ENV LOG_LEVEL CORS_ORIGINS QUEUE_POLL_INTERVAL_SEC QUEUE_MAX_CONCURRENCY ENABLE_SCHEDULER"

args=()
while IFS='=' read -r key rest; do
  # Skip blanks / comments
  [[ -z "$key" || "$key" =~ ^# ]] && continue
  # Strip surrounding whitespace
  key="${key// /}"
  value="${rest#\"}"; value="${value%\"}"
  # Skip empty values (don't clobber existing Fly secrets with "")
  [ -z "$value" ] && continue
  # Skip non-secret keys already in fly.toml
  for k in $NON_SECRET_KEYS; do
    if [ "$k" = "$key" ]; then continue 2; fi
  done
  args+=( "$key=$value" )
done < "$ENVFILE"

if [ ${#args[@]} -eq 0 ]; then
  echo "nothing to push"; exit 0
fi

echo "Pushing ${#args[@]} secrets to Fly app 3lakes-backend…"
fly secrets set "${args[@]}"
