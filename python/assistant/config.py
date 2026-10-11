from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from assistant.errors import AssistantError

SYSTEM_INSTRUCTION = (
    "You are Jarvis, a program that runs on this computer to help the user with school. "
    "You can make notes on their classes, and you can read those notes from the class files they have given you access to. "
    "Each class can contain assignments. An assignment folder holds the notes you write and any source files the user adds. "
    "You can read text, PDF, and Word sources, and you can see the names of other attached files. "
    "You can create assignment folders and note files. "
    "If the screen looks like a quiz or assignment question, answer the question. "
    "Use the class files, assignment notes, and source documents to answer questions and complete assignments. "
    "For a multiple-choice question, give the answer by letter and text, and briefly explain why. "
    "If the screen looks like a textbook or other class reading, use that screenshot to take notes on the class the textbook is from. "
    "Save class-wide notes in that class's notes.md. Save notes about one assignment in that assignment's notes.md, creating the assignment folder first if needed. "
    "If you are not sure which class you are working on, which assignment a note belongs to, or which information belongs to which class, ask. Do not file notes under the wrong class. "
    "Do not invent details that are not on the screen or in the class files. "
    "Keep the reply concise, and name any file you create or change."
)

DEFAULTS: dict[str, Any] = {
    "shortcut": {"modifiers": ["ctrl", "alt"], "key": "]"},
    "model": "gpt-5.4-mini",
    "max_output_tokens": 800,
    "image_max_edge": 1600,
    "jpeg_quality": 80,
    "image_detail": "high",
    "timeout_seconds": 45,
    "system_instruction": SYSTEM_INSTRUCTION,
    "user_prompt": "Look at this screenshot and help with school.",
    "popup": {"width": 400, "max_height": 520, "margin": 16},
    "classes_enabled": True,
    "classes_dir": "",
}

_MODIFIERS = {"ctrl", "alt", "cmd", "shift"}
_DETAILS = {"low", "high", "auto", "original"}


def default_config_path() -> Path:
    return Path.home() / ".config" / "mac-ai-assistant" / "config.json"


def merge_dict(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_dict(current, value)
        else:
            merged[key] = value
    return merged


def _require_int(data: Mapping[str, Any], key: str, low: int, high: int) -> None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise AssistantError(
            "config_error",
            f"Config field {key} must be an integer from {low} to {high}.",
        )


def validate_config(data: Mapping[str, Any]) -> None:
    shortcut = data.get("shortcut")
    if not isinstance(shortcut, dict):
        raise AssistantError("config_error", "Config field shortcut must be an object.")
    modifiers = shortcut.get("modifiers")
    if (
        not isinstance(modifiers, list)
        or not modifiers
        or any(not isinstance(item, str) or item not in _MODIFIERS for item in modifiers)
    ):
        raise AssistantError(
            "config_error",
            "Config shortcut.modifiers must be a list of ctrl, alt, cmd, and shift.",
        )
    key = shortcut.get("key")
    if not isinstance(key, str) or not key.strip() or any(char.isspace() for char in key):
        raise AssistantError(
            "config_error",
            "Config shortcut.key must be a Hammerspoon key name without spaces, such as ].",
        )

    model = data.get("model")
    if not isinstance(model, str) or not model.strip() or any(char.isspace() for char in model):
        raise AssistantError("config_error", "Config field model must be a model name.")

    _require_int(data, "max_output_tokens", 16, 4000)
    _require_int(data, "image_max_edge", 512, 2048)
    _require_int(data, "jpeg_quality", 40, 95)
    _require_int(data, "timeout_seconds", 5, 180)

    detail = data.get("image_detail")
    if detail not in _DETAILS:
        raise AssistantError(
            "config_error",
            "Config field image_detail must be low, high, auto, or original.",
        )

    instruction = data.get("system_instruction")
    prompt = data.get("user_prompt")
    if not isinstance(instruction, str) or not instruction.strip():
        raise AssistantError("config_error", "Config field system_instruction must be text.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise AssistantError("config_error", "Config field user_prompt must be text.")

    popup = data.get("popup")
    if not isinstance(popup, dict):
        raise AssistantError("config_error", "Config field popup must be an object.")
    for field, low, high in (("width", 280, 800), ("max_height", 200, 1000), ("margin", 0, 80)):
        value = popup.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise AssistantError(
                "config_error",
                f"Config field popup.{field} must be an integer from {low} to {high}.",
            )

    enabled = data.get("classes_enabled")
    if not isinstance(enabled, bool):
        raise AssistantError("config_error", "Config field classes_enabled must be true or false.")
    classes_dir = data.get("classes_dir")
    if not isinstance(classes_dir, str) or "\x00" in classes_dir or "\n" in classes_dir:
        raise AssistantError(
            "config_error",
            "Config field classes_dir must be a folder path, or an empty string for the default folder.",
        )
    if classes_dir.strip():
        from assistant.classes import resolved_classes_dir

        resolved_classes_dir(data)


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load the user config, falling back to built-in defaults when it is absent."""
    config_path = path or default_config_path()
    override: dict[str, Any] = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssistantError(
                "config_error",
                f"The config file is not valid JSON: {config_path}",
            ) from exc
        if not isinstance(loaded, dict):
            raise AssistantError("config_error", f"The config file must contain an object: {config_path}")
        override = loaded
    merged = merge_dict(DEFAULTS, override)
    validate_config(merged)
    return merged
