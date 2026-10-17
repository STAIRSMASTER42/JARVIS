"""The user's own writing. Jarvis can read it, and only the user can add to it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from assistant.classes import _assert_dedicated_folder
from assistant.errors import AssistantError, sanitize

WRITING_GUIDANCE = (
    "My writing is a separate file of the user's own writing. It is not a class and it is not class notes. "
    "The user adds every piece from the Classes window. You cannot create, edit, or delete that file. "
    "When the user asks you to write like them, call read_my_writing first and match their voice, rhythm, and wording. "
    "Do not imitate their writing unless they ask. Do not copy a piece verbatim unless they ask for that."
)

# About 1 million tokens, leaving the rest of the 1.2 million token window for the question and the answer.
_MAX_CHARS = 4_000_000
_FILENAME = "my-writing.md"


def writing_dir(classes_root: Path) -> Path:
    """Folder beside the classes folder, never inside a class."""
    classes = classes_root.resolve()
    path = (classes.parent / "writing").resolve()
    _assert_dedicated_folder(path)
    if path == classes or classes in path.parents or path in classes.parents:
        raise AssistantError("config_error", "My writing must stay outside the classes folder.")
    return path


def writing_file(classes_root: Path) -> Path:
    return writing_dir(classes_root) / _FILENAME


def writing_summary(classes_root: Path) -> str:
    path = writing_file(classes_root)
    count = piece_count(path)
    if count == 0:
        return "My writing: no pieces yet. The user adds them from the Classes window."
    label = "1 piece" if count == 1 else f"{count} pieces"
    return f"My writing ({label}, not a class). Read it with read_my_writing when the user asks you to write like them."


def piece_count(path: Path) -> int:
    if not path.is_file() or path.is_symlink():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("## "))


def add_writing(classes_root: Path, title: str, text: str) -> Path:
    """Append a piece the user wrote. Jarvis does not call this."""
    heading = " ".join(title.split())
    body = text.strip()
    if not heading:
        raise AssistantError("class_file", "Give this piece of writing a title.")
    if len(heading) > 120:
        raise AssistantError("class_file", "That title is too long.")
    if not body:
        raise AssistantError("class_file", "Paste the writing you want to add.")
    body = sanitize(body)
    if len(body) > _MAX_CHARS:
        raise AssistantError("class_file", "That piece of writing is too long to add in one step.")
    folder = writing_dir(classes_root)
    folder.mkdir(exist_ok=True)
    path = folder / _FILENAME
    if path.is_symlink():
        raise AssistantError("class_file", "My writing cannot be a link.")
    current = ""
    if path.is_file():
        current = path.read_text(encoding="utf-8", errors="replace")
    if not current.strip():
        current = "# My writing\n"
    addition = f"\n## {heading}\n\n{body}\n"
    updated = current.rstrip() + "\n" + addition
    if len(updated) > _MAX_CHARS:
        raise AssistantError("class_file", "My writing is full. The file cannot grow past its size limit.")
    path.write_text(updated, encoding="utf-8")
    return path


def like_me_prompt(classes_root: Path, text: str) -> str:
    """The user's request plus the whole My writing file and a style instruction."""
    if piece_count(writing_file(classes_root)) == 0:
        raise AssistantError("bad_request", "Add writing in My writing before using Write like me.")
    sample = read_my_writing(classes_root)
    return (
        f"{text.strip()}\n\n"
        "Write even closer to the sample text below. "
        "Use only words found in that text, except you may add a couple of words when one is needed. "
        "Use the phrase \"Including but not limited to\" as much as possible. "
        "In each writing assignment, include one comparison to lawn keeping, and choose a different comparison each time. "
        "First say a short comment, such as here is your essay. "
        "Then put only the writing after a line that is exactly ---essay--- and before a line that is exactly ---end---. "
        "The writing between those lines is plain text: no bold, no markdown, no asterisks, and no headings.\n\n"
        f"{sample}"
    )


def read_my_writing(classes_root: Path) -> str:
    path = writing_file(classes_root)
    if path.is_symlink() or not path.is_file():
        return "My writing is empty. The user adds writing from the Classes window. You cannot add it."
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text or piece_count(path) == 0:
        return "My writing is empty. The user adds writing from the Classes window. You cannot add it."
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[truncated]"
    return text


def writing_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "read_my_writing",
            "description": (
                "Read the user's My writing file. It is not a class. "
                "Use it when they ask you to write like them. You cannot add to or edit this file."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
