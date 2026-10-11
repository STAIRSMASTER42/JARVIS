#!/bin/bash
# Run the assistant CLI with the project virtualenv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  printf '%s\n' '{"ok":false,"code":"not_installed","error":"The Python environment is missing. Run scripts/install.sh."}'
  exit 1
fi

export PYTHONPATH="${ROOT}/python${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON}" -m assistant "$@"
