#!/bin/bash
# Store or replace this Mac's OpenAI API key in the login Keychain.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
KEY="${OPENAI_API_KEY:-}"

if [[ -z "${KEY}" ]]; then
  if [[ ! -t 0 ]]; then
    echo "Set OPENAI_API_KEY or run this script in a terminal." >&2
    exit 1
  fi
  read -r -s -p "OpenAI API key: " KEY
  echo
fi

if [[ -z "${KEY}" ]]; then
  echo "No key entered." >&2
  exit 1
fi

TRUST=()
if [[ -x "${PYTHON}" ]]; then
  TRUST+=(-T "${PYTHON}")
fi
TRUST+=(-T /usr/bin/security)

security add-generic-password -U \
  -s mac-ai-assistant-openai \
  -a charliebaker \
  -w "${KEY}" \
  "${TRUST[@]}" >/dev/null

unset KEY
echo "Stored the API key in Keychain (service mac-ai-assistant-openai, account charliebaker)."
echo "If macOS asks for Keychain access the first time you use the shortcut, choose Always Allow."
