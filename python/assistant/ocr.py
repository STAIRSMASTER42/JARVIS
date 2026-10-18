"""Read text from a screenshot on this Mac, then delete the image."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from assistant.errors import AssistantError, sanitize

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]
_MISSING = "Could not find the tesseract program. Install it with: brew install tesseract"


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
        if os.path.isfile(candidate):
            return candidate
    return None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _read(binary: str, path: Path, mode: str, runner: Runner) -> str:
    completed = runner([binary, str(path), "stdout", "--psm", mode, "--oem", "3"])
    text = (completed.stdout or "").strip()
    if completed.returncode != 0 and not text:
        detail = sanitize((completed.stderr or completed.stdout or "tesseract failed").strip())[:200]
        raise AssistantError("ocr_error", "The text could not be read. " + detail)
    return text


def read_image(path: Path, runner: Runner | None = None) -> str:
    """Return the words in an image. The image is deleted either way."""
    binary = find_tesseract()
    try:
        if not path.is_file() or path.stat().st_size < 32:
            raise AssistantError("ocr_error", "The screenshot was empty.")
        if not binary:
            raise AssistantError("ocr_error", _MISSING)
        run = runner or (lambda command: subprocess.run(command, capture_output=True, text=True, timeout=30, check=False))
        text = _read(binary, path, "6", run)
        if not text:
            text = _read(binary, path, "11", run)
        return text
    finally:
        _unlink(path)
