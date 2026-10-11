from __future__ import annotations

import subprocess
from pathlib import Path

from assistant.errors import SCREEN_PERMISSION_MESSAGE, AssistantError, sanitize


def sips_command(source: Path, destination: Path, max_edge: int, quality: int) -> list[str]:
    return [
        "/usr/bin/sips",
        "-s",
        "format",
        "jpeg",
        "-s",
        "formatOptions",
        str(quality),
        "--resampleHeightWidthMax",
        str(max_edge),
        str(source),
        "--out",
        str(destination),
    ]


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


def prepare_image(
    path: Path,
    max_edge: int,
    quality: int,
    keep: bool = False,
    runner: object | None = None,
) -> tuple[bytes, str]:
    """Resize a screenshot to a JPEG and delete the temporary files."""
    if not path.is_file():
        raise AssistantError("image_error", "The screenshot file could not be read.")

    raw = path.read_bytes()
    destination = path.with_name(path.stem + "-send.jpg")
    if len(raw) < 32:
        if not keep:
            _unlink(path)
        raise AssistantError("screenshot_permission", SCREEN_PERMISSION_MESSAGE)

    command = sips_command(path, destination, max_edge, quality)
    run = runner or subprocess.run
    try:
        completed = run(command, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        if not keep:
            _unlink(path)
            _unlink(destination)
        raise AssistantError("image_error", "Resizing the screenshot took too long.") from exc
    except OSError as exc:
        if not keep:
            _unlink(path)
            _unlink(destination)
        raise AssistantError("image_error", "Could not run the macOS image tool (sips).") from exc

    failed = completed.returncode != 0 or not destination.is_file()
    data = b""
    if not failed:
        data = destination.read_bytes()
        failed = len(data) < 32

    if not keep:
        _unlink(path)
        _unlink(destination)

    if failed:
        detail = sanitize((completed.stderr or completed.stdout or "sips failed").strip())[:200]
        raise AssistantError("image_error", "Could not prepare the screenshot. " + detail)
    if len(data) > 8 * 1024 * 1024:
        raise AssistantError(
            "image_error",
            "The screenshot is still too large to send. Lower image_max_edge in the config file.",
        )
    return data, "image/jpeg"
