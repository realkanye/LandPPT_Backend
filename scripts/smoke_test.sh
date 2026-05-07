#!/usr/bin/env bash
# =============================================================================
# LandPPT Backend — Smoke Test
# =============================================================================
# Drives the full PPT-generation flow end-to-end against a running server:
#   1. Health check
#   2. Submit a generation job
#   3. Poll until completed
#   4. Download HTML preview
#   5. Submit PPTX export job
#   6. Poll until completed
#   7. Download editable PPTX
#
# Usage:
#   bash scripts/smoke_test.sh
#   BASE_URL=http://my-server:8000 bash scripts/smoke_test.sh
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOPIC="${TOPIC:-人工智能在医疗领域的应用}"
SCENARIO="${SCENARIO:-technology}"
LANGUAGE="${LANGUAGE:-zh}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-600}"

# Colours
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

bail() { red "✗ $*"; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || bail "Required command missing: $1"
}

require curl
require python3

# JSON-field extractor: avoids dependency on jq.
jget() {
  local key="$1"
  python3 -c "import sys, json; v = json.load(sys.stdin).get('$key'); print('' if v is None else v)"
}

# -----------------------------------------------------------------------------
bold "=== LandPPT smoke test ==="
echo "Server:      $BASE_URL"
echo "Topic:       $TOPIC"
echo "Scenario:    $SCENARIO"
echo "Language:    $LANGUAGE"
echo

# -----------------------------------------------------------------------------
# Step 1: health
bold "[1/7] Health check"
HEALTH=$(curl -sf "$BASE_URL/v1/health" || bail "Cannot reach $BASE_URL/v1/health — is the server running?")
PROVIDER=$(echo "$HEALTH" | jget ai_provider)
STATUS=$(echo "$HEALTH"   | jget status)
[ "$STATUS" = "healthy" ] || bail "Server not healthy: $HEALTH"
green "  ok — status=healthy, ai_provider=$PROVIDER"
echo

# -----------------------------------------------------------------------------
# Step 2: submit
bold "[2/7] Submit generation job"
RESP=$(curl -sf -X POST "$BASE_URL/v1/presentations" \
  -H "Content-Type: application/json" \
  -d "{
    \"topic\":           \"$TOPIC\",
    \"scenario\":        \"$SCENARIO\",
    \"language\":        \"$LANGUAGE\"
  }") || bail "Submit failed"

JOB_ID=$(echo "$RESP"     | jget job_id)
PROJECT_ID=$(echo "$RESP" | jget project_id)
[ -n "$JOB_ID" ] && [ -n "$PROJECT_ID" ] || bail "Bad response: $RESP"
green "  ok — job_id=$JOB_ID  project_id=$PROJECT_ID"
echo

# -----------------------------------------------------------------------------
# Step 3: poll generation
bold "[3/7] Wait for generation to complete (≤ ${TIMEOUT_SECONDS}s)"
START=$(date +%s)
while true; do
  STATUS_JSON=$(curl -sf "$BASE_URL/v1/jobs/$JOB_ID")
  S=$(echo "$STATUS_JSON" | jget status)
  P=$(echo "$STATUS_JSON" | jget progress)
  printf "  %-9s progress=%s\n" "$S" "$P"
  case "$S" in
    completed)             green "  ok — generation finished"; echo; break ;;
    failed|cancelled)      ERR=$(echo "$STATUS_JSON" | jget error); bail "Generation $S: $ERR" ;;
  esac
  ELAPSED=$(( $(date +%s) - START ))
  [ "$ELAPSED" -gt "$TIMEOUT_SECONDS" ] && bail "Generation timed out after ${TIMEOUT_SECONDS}s"
  sleep "$POLL_INTERVAL"
done

# -----------------------------------------------------------------------------
# Step 4: HTML preview
bold "[4/7] Download HTML preview"
HTML_FILE="smoke_preview.html"
curl -sf "$BASE_URL/v1/presentations/$PROJECT_ID/download?format=html" -o "$HTML_FILE"
HTML_BYTES=$(wc -c < "$HTML_FILE" | tr -d ' ')
[ "$HTML_BYTES" -gt 1000 ] || bail "HTML preview too small: $HTML_BYTES bytes"
green "  ok — saved $HTML_FILE ($HTML_BYTES bytes)"
echo

# -----------------------------------------------------------------------------
# Step 5: submit PPTX export
bold "[5/7] Submit PPTX export job"
EXPORT_RESP=$(curl -sf -X POST "$BASE_URL/v1/presentations/$PROJECT_ID/exports?format=pptx") \
  || bail "PPTX export submit failed"
EXPORT_JOB_ID=$(echo "$EXPORT_RESP" | jget job_id)
[ -n "$EXPORT_JOB_ID" ] || bail "Bad export response: $EXPORT_RESP"
green "  ok — export job_id=$EXPORT_JOB_ID"
echo

# -----------------------------------------------------------------------------
# Step 6: poll export
bold "[6/7] Wait for PPTX export (≤ ${TIMEOUT_SECONDS}s)"
START=$(date +%s)
while true; do
  S=$(curl -sf "$BASE_URL/v1/jobs/$EXPORT_JOB_ID" | jget status)
  printf "  export status: %s\n" "$S"
  case "$S" in
    completed) green "  ok — export finished"; echo; break ;;
    failed|cancelled) bail "Export $S" ;;
  esac
  ELAPSED=$(( $(date +%s) - START ))
  [ "$ELAPSED" -gt "$TIMEOUT_SECONDS" ] && bail "Export timed out after ${TIMEOUT_SECONDS}s"
  sleep 3
done

# -----------------------------------------------------------------------------
# Step 7: download PPTX
bold "[7/7] Download PPTX file"
PPTX_FILE="smoke_output.pptx"
curl -sf "$BASE_URL/v1/jobs/$EXPORT_JOB_ID/download" -o "$PPTX_FILE"
PPTX_BYTES=$(wc -c < "$PPTX_FILE" | tr -d ' ')
[ "$PPTX_BYTES" -gt 5000 ] || bail "PPTX too small: $PPTX_BYTES bytes"

# Verify it's a real PPTX (zip with ppt/slides/slide*.xml)
SLIDE_COUNT=$(python3 -c "
import zipfile, sys
try:
    with zipfile.ZipFile('$PPTX_FILE') as z:
        slides = [n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
        print(len(slides))
except Exception as e:
    print('0')
")
[ "$SLIDE_COUNT" -ge 1 ] || bail "PPTX has no slide XML files (corrupt?)"
green "  ok — saved $PPTX_FILE ($PPTX_BYTES bytes, $SLIDE_COUNT slides)"

echo
green "=========================================="
green "  SMOKE TEST PASSED  "
green "=========================================="
echo
echo "Outputs:"
echo "  · $HTML_FILE   — open in a browser to preview the deck"
echo "  · $PPTX_FILE   — open in PowerPoint / Keynote / WPS to verify"
echo "                   that every text and shape is editable."
echo
echo "Project ID kept in MongoDB:  $PROJECT_ID"
echo "Re-download HTML any time:   curl '$BASE_URL/v1/presentations/$PROJECT_ID/download?format=html'"
