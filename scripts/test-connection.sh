#!/bin/bash
# Send a tiny text-only request to OpenAI. This uses a small amount of API credit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${HOME}/.config/mac-ai-assistant/config.json"
ARGS=(test-connection)
if [[ -f "${CONFIG}" ]]; then
  ARGS+=(--config "${CONFIG}")
fi

"${ROOT}/scripts/run.sh" "${ARGS[@]}"
