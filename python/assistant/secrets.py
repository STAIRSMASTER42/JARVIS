from __future__ import annotations

import os
import subprocess
from typing import Callable, Mapping, Sequence

from assistant.errors import MISSING_KEY_MESSAGE, AssistantError

SERVICE_NAME = "mac-ai-assistant"
ACCOUNT_NAME = "openai"


def keychain_command() -> list[str]:
    return [
        "/usr/bin/security",
        "find-generic-password",
        "-s",
        SERVICE_NAME,
        "-a",
        ACCOUNT_NAME,
        "-w",
    ]


Runner = Callable[..., subprocess.CompletedProcess[str]]


def resolve_api_key(
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> str:
    """Return the API key from the environment, then from the login Keychain.

    The key is never logged. Callers must avoid interpolating it into messages.
    """
    source = os.environ if env is None else env
    from_env = (source.get("OPENAI_API_KEY") or "").strip()
    if from_env:
        return from_env

    run = runner or subprocess.run
    try:
        completed = run(
            keychain_command(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssistantError(
            "missing_api_key",
            "Could not read the API key from Keychain. " + MISSING_KEY_MESSAGE,
        ) from exc

    if completed.returncode != 0:
        raise AssistantError("missing_api_key", MISSING_KEY_MESSAGE)
    key = (completed.stdout or "").strip()
    if not key:
        raise AssistantError("missing_api_key", MISSING_KEY_MESSAGE)
    return key


def command_mentions_key(argv: Sequence[str], key: str) -> bool:
    """Used by tests to prove the key is not placed on a command line."""
    if not key:
        return False
    return any(key in part for part in argv)
