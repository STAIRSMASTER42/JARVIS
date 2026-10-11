#!/bin/bash
# Unload the assistant without quitting other Hammerspoon configuration.
set -euo pipefail

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

if [[ -z "${HS_BIN}" ]]; then
  echo "The hs command is not available. Click the AI menu bar item and choose Quit Screen Assistant." >&2
  echo "To remove it from login, disable Launch Hammerspoon at login in Hammerspoon preferences." >&2
  exit 1
fi

"${HS_BIN}" -c 'if macAIAssistantStop then macAIAssistantStop() end'
echo "Screen Assistant stopped. Hammerspoon itself is still running."
echo "Click Reload Config in Hammerspoon to start it again, or run scripts/launch.sh."
