from __future__ import annotations

import base64
from typing import Any

from assistant.errors import EMPTY_RESPONSE_MESSAGE, AssistantError, map_exception


def image_data_url(data: bytes, mime: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_analyze_request(
    *,
    model: str,
    instructions: str,
    prompt: str,
    data_url: str,
    detail: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": instructions,
        "max_output_tokens": max_output_tokens,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        "detail": detail,
                    },
                ],
            }
        ],
    }


def build_followup_request(
    *,
    model: str,
    instructions: str,
    previous_response_id: str,
    text: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": instructions,
        "previous_response_id": previous_response_id,
        "max_output_tokens": max_output_tokens,
        "input": text,
    }


def build_connection_request(*, model: str, max_output_tokens: int = 16) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": "Reply with the single word ok.",
        "max_output_tokens": max_output_tokens,
        "input": "Reply with the single word ok.",
    }


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        text = block.get("text")
        return text if isinstance(text, str) else ""
    text = getattr(block, "text", None)
    return text if isinstance(text, str) else ""


def extract_text(response: Any) -> str:
    """Read assistant text from a Responses API result."""
    direct = response.get("output_text") if isinstance(response, dict) else getattr(response, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = response.get("output") if isinstance(response, dict) else getattr(response, "output", None)
    parts: list[str] = []
    for item in output or []:
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
            continue
        for block in content or []:
            text = _block_text(block).strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def response_id(response: Any) -> str:
    value = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
    return value.strip() if isinstance(value, str) else ""


def create_response(client: Any, payload: dict[str, Any]) -> Any:
    try:
        return client.responses.create(**payload)
    except Exception as exc:
        raise map_exception(exc) from None


def make_client(api_key: str, timeout_seconds: int) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AssistantError(
            "not_installed",
            "The OpenAI package is not installed. Run scripts/install.sh.",
        ) from exc
    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def complete(client: Any, payload: dict[str, Any]) -> tuple[str, str]:
    response = create_response(client, payload)
    text = extract_text(response)
    if not text:
        raise AssistantError("bad_response", EMPTY_RESPONSE_MESSAGE)
    return text, response_id(response)
