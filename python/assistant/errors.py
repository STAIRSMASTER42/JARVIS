from __future__ import annotations

import re
from typing import Any


class AssistantError(Exception):
    """A failure that should be shown to the user."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,})"
    r"|(Bearer\s+[A-Za-z0-9._\-]{8,})"
    r"|((?:api[_-]?key|authorization)['\"\s:=]{1,8}['\"][^'\"]{8,}['\"])",
    re.IGNORECASE,
)


def sanitize(text: str) -> str:
    """Remove credential-shaped substrings from text that might be displayed."""
    if not text:
        return ""
    return _SECRET.sub("[redacted]", text)


MISSING_KEY_MESSAGE = (
    "No OpenAI API key is available. Run scripts/install.sh to store one in "
    "Keychain, or set the OPENAI_API_KEY environment variable."
)
INVALID_KEY_MESSAGE = (
    "The OpenAI API key was rejected. Store a valid key with scripts/setup-key.sh, "
    "or set the OPENAI_API_KEY environment variable."
)
QUOTA_MESSAGE = (
    "OpenAI rejected the request because of billing or quota. Check the plan and "
    "billing for this API key, then try again."
)
NETWORK_MESSAGE = "Could not reach OpenAI. Check the internet connection and try again."
TIMEOUT_MESSAGE = (
    "The request timed out. Try again. If this keeps happening, increase "
    "timeout_seconds in ~/.config/mac-ai-assistant/config.json."
)
SCREEN_PERMISSION_MESSAGE = (
    "Could not capture the screen. Enable Screen Recording for Hammerspoon in "
    "System Settings → Privacy & Security → Screen Recording, then quit and reopen Hammerspoon."
)
EMPTY_RESPONSE_MESSAGE = (
    "The model returned an empty response. Try again, or choose another vision "
    "model in ~/.config/mac-ai-assistant/config.json."
)


def _provider_code(exc: BaseException) -> str:
    body: Any = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("code") or error.get("type") or "")
    return str(getattr(exc, "code", "") or "")


def map_exception(exc: BaseException) -> AssistantError:
    """Turn a provider or network exception into a safe, user-facing error."""
    if isinstance(exc, AssistantError):
        return exc

    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    provider_code = _provider_code(exc).lower()
    blob = sanitize(f"{exc}").lower()

    if name == "AuthenticationError" or status in (401, 403) or provider_code == "invalid_api_key":
        return AssistantError("invalid_api_key", INVALID_KEY_MESSAGE)
    if (
        name == "RateLimitError"
        or status in (402, 429)
        or provider_code
        in {
            "insufficient_quota",
            "billing_hard_limit_reached",
            "billing_not_active",
            "rate_limit_exceeded",
        }
    ):
        return AssistantError("quota", QUOTA_MESSAGE)
    if name in {"APITimeoutError", "TimeoutError", "ReadTimeout"} or status == 408:
        return AssistantError("timeout", TIMEOUT_MESSAGE)
    if name in {"APIConnectionError", "ConnectError", "ConnectionError"} or "nodename nor servname" in blob:
        return AssistantError("network", NETWORK_MESSAGE)
    if "timed out" in blob or "timeout" in blob:
        return AssistantError("timeout", TIMEOUT_MESSAGE)
    if "connection error" in blob or "network is unreachable" in blob or "name or service not known" in blob:
        return AssistantError("network", NETWORK_MESSAGE)
    if status == 400 or name in {"BadRequestError", "NotFoundError"}:
        detail = sanitize(str(exc))[:240]
        return AssistantError(
            "bad_request",
            "OpenAI rejected the request. Check the model name in the config file. " + detail,
        )
    detail = sanitize(str(exc))[:240]
    return AssistantError("api_error", "The OpenAI request failed. " + detail)
