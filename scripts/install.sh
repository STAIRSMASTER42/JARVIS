#!/bin/bash
# Install the screen assistant for the current macOS user.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="${HOME}/.config/mac-ai-assistant"
HS_DIR="${HOME}/.hammerspoon"
HS_LINK="${HS_DIR}/mac-ai-assistant"
MARKER="mac-ai-assistant (managed)"
NONINTERACTIVE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|--noninteractive)
      NONINTERACTIVE=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: scripts/install.sh [--yes]" >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This assistant only runs on macOS." >&2
  exit 1
fi

python_is_new_enough() {
  [[ -x "$1" ]] && "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
}

find_python() {
  local candidates=(
    /opt/homebrew/bin/python3.13
    /opt/homebrew/bin/python3.12
    /opt/homebrew/bin/python3.11
    /usr/local/bin/python3.13
    /usr/local/bin/python3.12
    /usr/local/bin/python3.11
    /opt/homebrew/bin/python3
    /usr/local/bin/python3
  )
  local bin
  for bin in "${candidates[@]}"; do
    if python_is_new_enough "${bin}"; then
      echo "${bin}"
      return 0
    fi
  done
  if command -v brew >/dev/null 2>&1; then
    echo "The OpenAI SDK needs Python 3.10 or newer. Installing Python 3.12..." >&2
    brew install python@3.12 >&2
    local installed
    installed="$(brew --prefix python@3.12)/bin/python3.12"
    if python_is_new_enough "${installed}"; then
      echo "${installed}"
      return 0
    fi
  fi
  echo "Python 3.10 or newer is required. Install it with: brew install python@3.12" >&2
  return 1
}

if [[ ! -d /Applications/Hammerspoon.app ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Hammerspoon is not installed, and Homebrew was not found." >&2
    echo "Install Hammerspoon from https://www.hammerspoon.org and run this script again." >&2
    exit 1
  fi
  echo "Installing Hammerspoon..."
  brew install --cask hammerspoon
fi

PYTHON_BIN="$(find_python)"
echo "Using ${PYTHON_BIN}"
"${PYTHON_BIN}" -m venv "${ROOT}/.venv"
"${ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${ROOT}/.venv/bin/python" -m pip install -r "${ROOT}/requirements.txt"

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_DIR}/config.json" ]]; then
  cp "${ROOT}/config.example.json" "${CONFIG_DIR}/config.json"
  echo "Wrote ${CONFIG_DIR}/config.json"
else
  echo "Kept existing ${CONFIG_DIR}/config.json"
fi

PROJECT_ROOT="${ROOT}" "${ROOT}/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

path = Path.home() / ".config" / "mac-ai-assistant" / "install.json"
path.write_text(json.dumps({"project_root": os.environ["PROJECT_ROOT"]}, indent=2) + "\n", encoding="utf-8")
PY

chmod +x "${ROOT}/scripts/"*.sh

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  "${ROOT}/scripts/setup-key.sh"
elif [[ "${NONINTERACTIVE}" -eq 0 ]]; then
  echo
  echo "Each Mac stores its own API key in Keychain. Nothing is written into the repository."
  if "${ROOT}/scripts/setup-key.sh"; then
    true
  else
    echo "Key setup was skipped or failed. You can run scripts/setup-key.sh later."
  fi
else
  echo "No OPENAI_API_KEY in the environment. Run scripts/setup-key.sh before using the assistant."
fi

mkdir -p "${HS_DIR}"
ln -sfn "${ROOT}/hammerspoon" "${HS_LINK}"

BLOCK="$(cat <<EOF
-- ${MARKER}
require("hs.ipc")
local macAIOk, macAIErr = pcall(function()
  local macAI = dofile(os.getenv("HOME") .. "/.hammerspoon/mac-ai-assistant/mac_ai_assistant.lua")
  macAI.start()
  _G.macAIAssistantStop = macAI.stop
end)
if not macAIOk then
  print("mac-ai-assistant failed to start: " .. tostring(macAIErr))
end
EOF
)"

INIT="${HS_DIR}/init.lua"
if [[ ! -f "${INIT}" ]]; then
  printf '%s\n' "${BLOCK}" > "${INIT}"
  echo "Created ${INIT}"
elif ! grep -F -q "${MARKER}" "${INIT}"; then
  printf '\n%s\n' "${BLOCK}" >> "${INIT}"
  echo "Added the assistant to ${INIT}"
else
  echo "Hammerspoon config already loads the assistant."
fi

if osascript >/dev/null <<'APPLESCRIPT'
tell application "System Events"
  if not (exists login item "Hammerspoon") then
    make login item at end with properties {path:"/Applications/Hammerspoon.app", hidden:false}
  end if
end tell
APPLESCRIPT
then
  echo "Hammerspoon is set to open at login."
else
  echo "Could not add the login item automatically."
  echo "Open Hammerspoon and enable Launch Hammerspoon at login."
fi

open -a Hammerspoon || true

HS_BIN=""
for candidate in \
  /Applications/Hammerspoon.app/Contents/Frameworks/hs/hs \
  /opt/homebrew/bin/hs \
  /usr/local/bin/hs
do
  if [[ -x "${candidate}" ]]; then
    HS_BIN="${candidate}"
    break
  fi
done

if [[ -n "${HS_BIN}" ]]; then
  "${HS_BIN}" -c "hs.reload()" || echo "Hammerspoon is open. Reload its config from the menu bar if the shortcut is not active yet."
else
  echo "Reload Hammerspoon from its menu bar (Reload Config) after granting permissions."
fi

cat <<EOF

Installed. Finish these one-time macOS prompts:

1. Accessibility — System Settings → Privacy & Security → Accessibility → enable Hammerspoon.
   Required for the global shortcut.
2. Screen Recording — System Settings → Privacy & Security → Screen Recording → enable Hammerspoon.
   Required to capture the display. Then quit and reopen Hammerspoon.
3. Keychain — the first request may ask to allow python to read the API key. Choose Always Allow.

Shortcut: Control + Option + ]
Menu bar: the "AI" item can disable the shortcut or quit the assistant.
Quit from a shell: scripts/quit.sh
API check: scripts/test-connection.sh
EOF
