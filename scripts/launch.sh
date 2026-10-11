#!/bin/bash
# Open Hammerspoon and reload its config so the assistant is running.
set -euo pipefail

open -a Hammerspoon

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
  "${HS_BIN}" -c "hs.reload()"
  echo "Hammerspoon reloaded. Press Control-Option-] to ask about the screen."
else
  echo "Hammerspoon is open. If the shortcut does nothing, click its menu bar icon and choose Reload Config."
fi
