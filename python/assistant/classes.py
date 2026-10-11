"""Local class notes the assistant can read and edit.

Files stay in one folder on this Mac. Tool calls cannot write outside it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from assistant.errors import AssistantError, sanitize

CLASS_GUIDANCE = (
    "The class files you can read and edit are cataloged below. They are on this computer, and they count as known context. "
    "Read the relevant files before you answer a question or complete an assignment. "
    "When a textbook screenshot belongs to a class, write the notes into that class's notes.md. "
    "When the user asks you to add a class, create course.md, notes.md, and assignments.md in a new folder. "
    "If you cannot tell which class a screen or a fact belongs to, ask instead of guessing. "
    "Do not invent course details, due dates, or notes that are not in the files or on the screen. "
    "You can create and edit files only inside this classes folder. "
    "After you create or edit a file, name the file path in your reply."
)

README_TEXT = """# Classes

Jarvis reads this folder to help with school. It answers quiz and assignment screens using these notes, and it saves textbook screenshots into the matching class. If it is not sure which class a screen belongs to, it asks.

Each class is a folder:

- `course.md` — name, term, instructor, schedule, and what the class is about
- `notes.md` — notes you or the assistant save
- `assignments.md` — assignments, due dates, and what you have finished

Add a class from the project directory:

```bash
scripts/run.sh classes add --title "Biology 101" --term "Fall 2026"
```

You can also ask in the popup: "Add my Biology 101 class."
"""

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_SUFFIXES = {".md", ".txt", ".json", ".csv"}
_MAX_CHARS = 120_000
_MAX_SEARCH_HITS = 30
_FORBIDDEN_ROOTS = {
    Path("/"),
    Path("/tmp"),
    Path("/private/tmp"),
    Path("/Users"),
}


def default_classes_dir() -> Path:
    return Path.home() / "Documents" / "mac-ai-assistant" / "classes"


def resolved_classes_dir(config: Mapping[str, Any]) -> Path:
    raw = config.get("classes_dir") or ""
    if not isinstance(raw, str):
        raise AssistantError("config_error", "Config field classes_dir must be a folder path or an empty string.")
    path = Path(raw).expanduser() if raw.strip() else default_classes_dir()
    if not path.is_absolute():
        path = Path.home() / path
    resolved = path.resolve()
    _assert_dedicated_folder(resolved)
    return resolved


def _assert_dedicated_folder(path: Path) -> None:
    home = Path.home().resolve()
    forbidden = _FORBIDDEN_ROOTS | {
        home,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
    }
    if path in forbidden:
        raise AssistantError(
            "config_error",
            "classes_dir must be a dedicated folder, such as ~/Documents/mac-ai-assistant/classes.",
        )


def with_class_context(instructions: str, catalog_text: str) -> str:
    return instructions.rstrip() + "\n\n" + CLASS_GUIDANCE + "\n\n" + catalog_text.strip() + "\n"


def ensure_workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
    return root


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    slug = slug[:60].strip("-")
    if not slug or not _NAME.match(slug):
        raise AssistantError("class_file", "The class name needs letters or numbers.")
    return slug


def _course_template(title: str, term: str, instructor: str, schedule: str) -> str:
    return (
        f"# {title}\n\n"
        f"- Term: {term}\n"
        f"- Instructor: {instructor}\n"
        f"- Schedule: {schedule}\n\n"
        "## What this class is about\n\n"
        "## Current topics\n"
    )


def add_course(
    root: Path,
    title: str,
    *,
    term: str = "",
    instructor: str = "",
    schedule: str = "",
) -> Path:
    cleaned = title.strip()
    if not cleaned:
        raise AssistantError("class_file", "A class needs a title.")
    ensure_workspace(root)
    folder = root / slugify(cleaned)
    if folder.exists():
        raise AssistantError("class_file", f"{folder.name} already exists. Edit the files in that folder.")
    folder.mkdir()
    (folder / "course.md").write_text(
        _course_template(cleaned, term.strip(), instructor.strip(), schedule.strip()),
        encoding="utf-8",
    )
    (folder / "notes.md").write_text(f"# Notes — {cleaned}\n", encoding="utf-8")
    (folder / "assignments.md").write_text(f"# Assignments — {cleaned}\n", encoding="utf-8")
    return folder


def course_title(folder: Path) -> str:
    course_file = folder / "course.md"
    if course_file.is_file() and not course_file.is_symlink():
        for line in course_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                if title:
                    return title
    return folder.name


def catalog(root: Path) -> str:
    lines = [f"Classes folder: {root}"]
    if not root.is_dir():
        lines.append("The classes folder has not been created yet.")
        return "\n".join(lines)
    courses = sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
    )
    if not courses:
        lines.append("No class folders yet.")
        return "\n".join(lines)
    lines.append("Classes:")
    for course in courses:
        files = sorted(
            path.name
            for path in course.iterdir()
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in _SUFFIXES
        )
        listed = ", ".join(files) if files else "(no text files yet)"
        lines.append(f"- {course.name}: {course_title(course)} — files: {listed}")
    return "\n".join(lines)


def class_tools() -> list[dict[str, Any]]:
    path_schema = {"type": "string", "description": "Path relative to the classes folder, such as biology-101/notes.md."}
    return [
        _tool(
            "list_class_files",
            "List class folders and the text files inside them.",
            {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        ),
        _tool(
            "read_class_file",
            "Read one class file before answering or editing it.",
            _object({"path": path_schema}, ["path"]),
        ),
        _tool(
            "write_class_file",
            "Create or replace a class file. Use this for a new class or a full rewrite the user asked for.",
            _object(
                {
                    "path": path_schema,
                    "content": {"type": "string", "description": "The full new text of the file."},
                },
                ["path", "content"],
            ),
        ),
        _tool(
            "edit_class_file",
            "Replace one exact passage in a class file. old_text must match once.",
            _object(
                {
                    "path": path_schema,
                    "old_text": {"type": "string", "description": "The exact existing passage to replace."},
                    "new_text": {"type": "string", "description": "The replacement passage."},
                },
                ["path", "old_text", "new_text"],
            ),
        ),
        _tool(
            "search_class_files",
            "Find a phrase across class files.",
            _object(
                {"query": {"type": "string", "description": "Text to search for, case-insensitive."}},
                ["query"],
            ),
        ),
    ]


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": parameters,
        "strict": True,
    }


class ClassWorkspace:
    """Runs class-file tools and remembers which files changed."""

    def __init__(self, root: Path) -> None:
        self.root = ensure_workspace(root)
        self.changed: list[str] = []

    def dispatch(self, name: str, arguments: str | Mapping[str, Any]) -> str:
        try:
            payload = _arguments(arguments)
            if name == "list_class_files":
                return catalog(self.root)
            if name == "read_class_file":
                return self._read(str(payload.get("path", "")))
            if name == "write_class_file":
                return self._write(str(payload.get("path", "")), str(payload.get("content", "")))
            if name == "edit_class_file":
                return self._edit(
                    str(payload.get("path", "")),
                    str(payload.get("old_text", "")),
                    str(payload.get("new_text", "")),
                )
            if name == "search_class_files":
                return self._search(str(payload.get("query", "")))
            return "That class file tool is not available."
        except AssistantError as exc:
            return exc.message
        except OSError:
            return "That class file could not be read or written."

    def _read(self, relative: str) -> str:
        path = resolve_class_file(self.root, relative)
        if not path.is_file():
            return "That file does not exist yet."
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > _MAX_CHARS:
            return text[:_MAX_CHARS] + "\n\n[truncated]"
        return text

    def _write(self, relative: str, content: str) -> str:
        path = resolve_class_file(self.root, relative)
        cleaned = _bounded_text(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cleaned, encoding="utf-8")
        stored = _relative(self.root, path)
        self._mark(stored)
        return f"Wrote {stored}."

    def _edit(self, relative: str, old_text: str, new_text: str) -> str:
        if not old_text:
            raise AssistantError("class_file", "old_text must be the passage to replace.")
        path = resolve_class_file(self.root, relative)
        if not path.is_file():
            return "That file does not exist yet. Use write_class_file to create it."
        current = path.read_text(encoding="utf-8", errors="replace")
        count = current.count(old_text)
        if count == 0:
            return "That text was not found in the file."
        if count > 1:
            return f"That text appears {count} times. Include more surrounding text so it matches once."
        updated = _bounded_text(current.replace(old_text, new_text, 1))
        path.write_text(updated, encoding="utf-8")
        stored = _relative(self.root, path)
        self._mark(stored)
        return f"Updated {stored}."

    def _search(self, query: str) -> str:
        needle = query.strip()
        if len(needle) < 2:
            return "The search needs at least two characters."
        folded = needle.casefold()
        hits: list[str] = []
        for path in _text_files(self.root):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                if folded in line.casefold():
                    snippet = line.strip()
                    if len(snippet) > 180:
                        snippet = snippet[:180] + "…"
                    hits.append(f"{_relative(self.root, path)}:{number}: {snippet}")
                    if len(hits) >= _MAX_SEARCH_HITS:
                        return "\n".join(hits) + "\n[search stopped at 30 matches]"
        return "\n".join(hits) if hits else "No matches."

    def _mark(self, relative: str) -> None:
        if relative not in self.changed:
            self.changed.append(relative)


def resolve_class_file(root: Path, relative: str) -> Path:
    raw = relative.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise AssistantError(
            "class_file",
            "Use a path inside the classes folder, such as biology-101/notes.md.",
        )
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or not _NAME.match(part) for part in parts):
        raise AssistantError("class_file", "That path is not allowed in the classes folder.")
    if len(parts) > 4:
        raise AssistantError("class_file", "Class files can be nested at most four levels deep.")
    suffix = Path(parts[-1]).suffix.lower()
    if suffix not in _SUFFIXES:
        raise AssistantError("class_file", "Class files must end in .md, .txt, .json, or .csv.")

    root_resolved = root.resolve()
    current = root_resolved
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise AssistantError("class_file", "That path is not allowed in the classes folder.")
        if current.exists() and not current.is_dir():
            raise AssistantError("class_file", "That path is not a folder.")
    candidate = current / parts[-1]
    if candidate.is_symlink():
        raise AssistantError("class_file", "That path is not allowed in the classes folder.")
    if candidate.exists():
        resolved = candidate.resolve()
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise AssistantError("class_file", "That path is outside the classes folder.")
    return candidate


def _arguments(arguments: str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise AssistantError("class_file", "The tool arguments were not valid JSON.") from exc
    else:
        decoded = arguments
    if not isinstance(decoded, dict):
        raise AssistantError("class_file", "The tool arguments must be an object.")
    return decoded


def _bounded_text(content: str) -> str:
    cleaned = sanitize(content)
    if len(cleaned) > _MAX_CHARS:
        raise AssistantError("class_file", "That file is too large to write in one step.")
    return cleaned


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _text_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in _SUFFIXES:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        found.append(path)
        if len(found) >= 200:
            break
    return found


def append_change_note(text: str, changed: list[str]) -> str:
    if not changed:
        return text
    note = "Updated " + ", ".join(changed) + "."
    if note in text:
        return text
    return text.rstrip() + "\n\n" + note
