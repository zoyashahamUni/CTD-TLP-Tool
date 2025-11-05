#!/usr/bin/env bash
set -euo pipefail

# --- Config ---
DEFAULT_MODEL="model/shoppingCartFixed210925.smv"
RESULTS_DIR="results"

# --- Args ---
MODEL_PATH="${1:-$DEFAULT_MODEL}"

# --- Check model exists ---
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "❌ Model not found: $MODEL_PATH"
  echo "Usage: $0 [path/to/model.smv]"
  exit 1
fi

# --- Find NuXmv ---
# 1) use NU_XMV env var if provided
# 2) else try system PATH
NUXMV_BIN="${NU_XMV:-$(command -v nuxmv || true)}"

if [[ -z "$NUXMV_BIN" ]]; then
  echo "❌ Could not find 'nuxmv' in PATH."
  echo "Set env var NU_XMV to your nuXmv binary or add it to PATH."
  echo "Example:"
  echo "  export NU_XMV=\"/usr/local/bin/nuxmv\""
  exit 1
fi

# --- Prepare results dir ---
mkdir -p "$RESULTS_DIR"
STAMP="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="${RESULTS_DIR}/run_${STAMP}.log"

echo "▶ Running: $NUXMV_BIN $MODEL_PATH"
echo "   Log:    $LOG_FILE"
echo "-----------------------------------------"

"$NUXMV_BIN" "$MODEL_PATH" | tee "$LOG_FILE"

echo "-----------------------------------------"
echo "✅ Done. Output saved to: $LOG_FILE"
