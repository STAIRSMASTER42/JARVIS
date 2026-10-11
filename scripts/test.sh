#!/bin/bash
# Run the non-GUI unit tests. They do not call OpenAI and do not capture the screen.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

export PYTHONPATH="${ROOT}/python${PYTHONPATH:+:${PYTHONPATH}}"
cd "${ROOT}"
"${PYTHON}" -m unittest discover -s python/tests -v
