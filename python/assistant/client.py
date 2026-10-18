from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from assistant.errors import EMPTY_RESPONSE_MESSAGE, AssistantError, map_exception
from assistant.writing import _MAX_CHARS as _WRITING_MAX_CHARS


def research_reasoning() -> dict[str, str]:
    """High reasoning effort, matching an academic research request."""
    return {"effort": "high"}


def web_search_tool() -> dict[str, Any]:
    """Ask OpenAI to search the public web. This Mac does not fetch the page."""
    return {"type": "web_search", "external_web_access": True, "search_context_size": "medium"}


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
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "reasoning": research_reasoning(),
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
    if tools:
        payload["tools"] = tools
    return payload


def build_followup_request(
    *,
    model: str,
    instructions: str,
    text: str,
    max_output_tokens: int,
    previous_response_id: str = "",
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "reasoning": research_reasoning(),
        "max_output_tokens": max_output_tokens,
        "input": text,
    }
    continued = previous_response_id.strip()
    if continued:
        payload["previous_response_id"] = continued
    if tools:
        payload["tools"] = tools
    return payload


CONTINUE_IMAGE_PROMPT = (
    "Another screenshot of the same schoolwork. "
    "Use the earlier screenshots, this conversation, and the class files as context. "
    "If this is a quiz or assignment question, answer it. "
    "If this is textbook reading, take notes for the class it belongs to. "
    "If you are unsure which class, ask."
)


def analyze_prompt(user_prompt: str, note: str = "") -> str:
    """First-screenshot prompt, with any text the user typed in the popup."""
    cleaned = note.strip()
    if not cleaned:
        return user_prompt
    return cleaned + "\n\n" + user_prompt


def continue_image_prompt(note: str = "") -> str:
    """Continue-screenshot prompt, with any text the user typed in the popup."""
    cleaned = note.strip()
    if not cleaned:
        return CONTINUE_IMAGE_PROMPT
    return cleaned + "\n\n" + CONTINUE_IMAGE_PROMPT


def build_continue_image_request(
    *,
    model: str,
    instructions: str,
    previous_response_id: str,
    prompt: str,
    data_url: str,
    detail: str,
    max_output_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "reasoning": research_reasoning(),
        "previous_response_id": previous_response_id,
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
    if tools:
        payload["tools"] = tools
    return payload


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


def _citation(note: Any) -> str:
    kind = note.get("type") if isinstance(note, dict) else getattr(note, "type", None)
    if kind != "url_citation":
        return ""
    url = note.get("url") if isinstance(note, dict) else getattr(note, "url", None)
    title = note.get("title") if isinstance(note, dict) else getattr(note, "title", None)
    if not isinstance(url, str) or not url.strip():
        return ""
    url = url.strip()
    if isinstance(title, str) and title.strip() and title.strip() != url:
        return f"{title.strip()} ({url})"
    return url


def _sources(response: Any) -> list[str]:
    output = response.get("output") if isinstance(response, dict) else getattr(response, "output", None)
    found: list[str] = []
    for item in output or []:
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        for block in content or []:
            if isinstance(block, str):
                continue
            notes = block.get("annotations") if isinstance(block, dict) else getattr(block, "annotations", None)
            for note in notes or []:
                line = _citation(note)
                if line and line not in found:
                    found.append(line)
    return found


def _with_sources(text: str, sources: list[str]) -> str:
    fresh = [line for line in sources if line not in text and line[line.rfind("(") + 1 :].rstrip(")") not in text]
    if not fresh:
        return text
    listed = "\n".join(f"- {line}" for line in fresh)
    return text.rstrip() + "\n\nSources:\n" + listed


def extract_text(response: Any) -> str:
    """Read assistant text from a Responses API result."""
    sources = _sources(response)
    direct = response.get("output_text") if isinstance(response, dict) else getattr(response, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return _with_sources(direct.strip(), sources)

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
    return _with_sources("\n".join(parts).strip(), sources)


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


def _field(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def function_calls(response: Any) -> list[dict[str, str]]:
    """Return function tool calls from a Responses API result."""
    output = _field(response, "output")
    calls: list[dict[str, str]] = []
    for item in output or []:
        if _field(item, "type") != "function_call":
            continue
        call_id = _field(item, "call_id")
        name = _field(item, "name")
        arguments = _field(item, "arguments")
        if not isinstance(call_id, str) or not call_id:
            continue
        if not isinstance(name, str) or not name:
            continue
        calls.append(
            {
                "call_id": call_id,
                "name": name,
                "arguments": arguments if isinstance(arguments, str) else "",
            }
        )
    return calls


def complete_with_tools(
    client: Any,
    payload: dict[str, Any],
    execute: Callable[[str, str], str],
    *,
    max_rounds: int = 50,
) -> tuple[str, str]:
    """Call the model, run class-file tools, and repeat until it returns text."""
    response = create_response(client, payload)
    for round_index in range(max_rounds + 1):
        calls = function_calls(response)
        if not calls:
            text = extract_text(response)
            if not text:
                raise AssistantError("bad_response", EMPTY_RESPONSE_MESSAGE)
            return text, response_id(response)
        if round_index == max_rounds:
            break
        outputs = []
        for call in calls:
            result = execute(call["name"], call["arguments"])
            if not isinstance(result, str):
                result = str(result)
            limit = _WRITING_MAX_CHARS if call["name"] == "read_my_writing" else 12_000
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": result[:limit],
                }
            )
        identifier = response_id(response)
        if not identifier:
            raise AssistantError("bad_response", EMPTY_RESPONSE_MESSAGE)
        response = create_response(
            client,
            {
                "model": payload["model"],
                "previous_response_id": identifier,
                "reasoning": payload.get("reasoning") or research_reasoning(),
                "input": outputs,
                "tools": payload.get("tools") or [],
                "max_output_tokens": payload["max_output_tokens"],
            },
        )
    raise AssistantError(
        "bad_response",
        "The assistant used class files too many times without finishing. Try the question again.",
    )
