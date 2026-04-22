#!/usr/bin/env bash
# Auto-summary checkpoint: every 14th user prompt, inject an instruction
# telling Claude to write a timestamped session summary to sessions/.
# Reads UserPromptSubmit hook JSON from stdin (ignored — counter only).

set -euo pipefail

PROJECT_ROOT="/home/user/3-Lakes-Logistics"
COUNTER_FILE="$PROJECT_ROOT/.claude/.prompt-counter"
SESSIONS_DIR="$PROJECT_ROOT/sessions"
INTERVAL=14

# Drain stdin so the hook doesn't stall if Claude pipes large payloads
cat >/dev/null 2>&1 || true

# Initialize counter if missing
[ -f "$COUNTER_FILE" ] || echo 0 > "$COUNTER_FILE"

COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

if [ $((COUNT % INTERVAL)) -eq 0 ]; then
  mkdir -p "$SESSIONS_DIR"
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  FN=$(date -u +"%Y-%m-%d_%H%M")
  FILE="$SESSIONS_DIR/${FN}_session-summary.md"
  # Emit JSON on stdout to inject an instruction into Claude's context
  printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"AUTO-SUMMARY CHECKPOINT (prompt #%s, every-%sth trigger). Before responding to the user, write a session summary to %s covering: (1) work completed since the last summary, (2) files touched, (3) tables/schemas designed, (4) commits on the current branch, (5) pending tasks. Start the file with a line reading: Filed: %s. Use the Write tool. Then answer the users prompt normally."},"systemMessage":"Auto-summary checkpoint (#%s) writing session summary to sessions/"}\n' \
    "$COUNT" "$INTERVAL" "$FILE" "$TS" "$COUNT"
fi
