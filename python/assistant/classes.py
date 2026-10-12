"""Local class notes the assistant can read and edit.

Files stay in one folder on this Mac. Tool calls cannot write outside it.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from assistant.errors import AssistantError, sanitize

CLASS_GUIDANCE = (
    "The class files you can read and edit are cataloged below. They are on this computer, and they count as known context. "
    "Layout: <class>/notes.md holds class notes. "
    "<class>/assignments/<assignment>/assignment.md describes one assignment, and notes.md in that folder holds its notes. "
    "<class>/assignments/<assignment>/sources/ holds any files the user attached. "
    "Read the relevant notes and sources before you answer a question or complete an assignment. "
    "Create an assignment folder when the user names an assignment or when a screenshot is clearly about one. "
    "Write textbook notes that belong to an assignment into that assignment's notes.md, and other textbook notes into the class notes.md. "
    "You can create and edit note files, and you can delete a class or assignment folder when the user asks you to remove it. "
    "Deleting a folder removes the notes and source files inside it. Do not delete a folder unless the user asked. "
    "The user adds source files of any type from the Classes window. "
    "My writing is not a class. Only the user adds to that file. Read it when they ask you to write like them. "
    "You can read text, PDF, and Word sources. For other files, use the file name and say when the contents could not be extracted. "
    "If you cannot tell which class or assignment a screen belongs to, ask instead of guessing. "
    "Do not invent course details, due dates, or notes that are not in the files or on the screen. "
    "After you create, edit, or delete a file or folder, name that path in your reply."
)

README_TEXT = """# Classes

Jarvis reads this folder to help with school. It answers quiz and assignment screens using these notes, and it saves textbook screenshots into the matching class. If it is not sure which class a screen belongs to, it asks.

Each class is a folder:

- `course.md` — name, term, instructor, schedule, and what the class is about
- `notes.md` — notes for the class
- `assignments/<name>/` — one assignment, with `notes.md` and a `sources` folder for any files you add

Add a class from the project directory:

```bash
scripts/run.sh classes add --title "Biology 101" --term "Fall 2026"
```

You can also ask in the popup: "Add my Biology 101 class."
"""

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv"}
_SOURCE_SUFFIXES = {".pdf", ".doc", ".docx"}
_SUFFIXES = _TEXT_SUFFIXES | _SOURCE_SUFFIXES
_MAX_CHARS = 120_000
_MAX_SOURCE_BYTES = 25 * 1024 * 1024
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
    (folder / "assignments").mkdir()
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


def _course_dir(root: Path, class_folder: str) -> Path:
    if not isinstance(class_folder, str) or not _NAME.match(class_folder):
        raise AssistantError("class_file", "That class folder name is not allowed.")
    course = root.resolve() / class_folder
    if course.is_symlink() or not course.is_dir():
        raise AssistantError(
            "class_file",
            "That class folder does not exist. Ask which class this belongs to.",
        )
    return course


def _assignment_dir(root: Path, class_folder: str, assignment_folder: str) -> Path:
    if not isinstance(assignment_folder, str) or not _NAME.match(assignment_folder):
        raise AssistantError("class_file", "That assignment folder name is not allowed.")
    folder = _course_dir(root, class_folder) / "assignments" / assignment_folder
    if folder.is_symlink() or not folder.is_dir():
        raise AssistantError("class_file", "That assignment does not exist yet.")
    resolved = folder.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise AssistantError("class_file", "That path is outside the classes folder.")
    return folder


def _heading(path: Path, fallback: str) -> str:
    if path.is_file() and not path.is_symlink():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                if title:
                    return title
    return fallback


def _due_line(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("- due:"):
            return line.split(":", 1)[1].strip()
    return ""


def _unique_source(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for number in range(2, 100):
        candidate = folder / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise AssistantError("class_file", "Too many files share that name.")


def add_assignment(root: Path, class_folder: str, title: str, due: str = "") -> Path:
    """Create one assignment folder with notes and a place for source documents."""
    cleaned = title.strip()
    if not cleaned:
        raise AssistantError("class_file", "An assignment needs a title.")
    course = _course_dir(root, class_folder)
    folder = course / "assignments" / slugify(cleaned)
    if folder.exists():
        raise AssistantError("class_file", f"{folder.name} already exists in {course.name}.")
    folder.mkdir(parents=True)
    (folder / "sources").mkdir()
    due_line = due.strip() or "unknown"
    (folder / "assignment.md").write_text(
        f"# {cleaned}\n\n- Due: {due_line}\n\n## What this assignment asks\n",
        encoding="utf-8",
    )
    (folder / "notes.md").write_text(f"# Notes — {cleaned}\n", encoding="utf-8")
    return folder


def save_source(root: Path, class_folder: str, assignment_folder: str, filename: str, data: bytes) -> Path:
    """Store a file the user attached to an assignment."""
    if not data:
        raise AssistantError("class_file", "That file is empty.")
    if len(data) > _MAX_SOURCE_BYTES:
        raise AssistantError("class_file", "That file is larger than 25 MB.")
    safe_name = source_filename(filename)
    assignment = _assignment_dir(root, class_folder, assignment_folder)
    sources = assignment / "sources"
    sources.mkdir(exist_ok=True)
    destination = _unique_source(sources, safe_name)
    destination.write_bytes(data)
    return destination


def source_filename(filename: str) -> str:
    base = Path(str(filename).replace("\\", "/")).name.replace("\x00", "").strip()
    if not base or base in {".", ".."} or base.startswith("."):
        raise AssistantError("class_file", "That file needs a name.")
    cleaned = re.sub(r"\s+", "-", base)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", cleaned).strip(".-")
    if len(cleaned) > 80:
        suffix = Path(cleaned).suffix[:16]
        stem = Path(cleaned).stem[: 80 - len(suffix)].strip(".-") or "file"
        cleaned = f"{stem}{suffix}"
    if not cleaned or not _NAME.match(cleaned):
        raise AssistantError("class_file", "That file needs a name.")
    return cleaned


def list_assignments(root: Path, class_folder: str) -> list[dict[str, str]]:
    course = _course_dir(root, class_folder)
    assignments = course / "assignments"
    if not assignments.is_dir() or assignments.is_symlink():
        return []
    found: list[dict[str, str]] = []
    for path in sorted((item for item in assignments.iterdir() if item.is_dir() and not item.is_symlink()), key=lambda item: item.name):
        found.append(
            {
                "slug": path.name,
                "title": _heading(path / "assignment.md", path.name),
                "due": _due_line(path / "assignment.md"),
            }
        )
    return found


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
        lines.append(
            f"- {course.name}: {course_title(course)} — files: {listed} — assignments: {_catalog_assignments(course)}"
        )
    return "\n".join(lines)


def _catalog_assignments(course: Path) -> str:
    items = list_assignments(course.parent, course.name)
    if not items:
        return "none yet"
    parts: list[str] = []
    for item in items:
        folder = course / "assignments" / item["slug"]
        source_dir = folder / "sources"
        sources: list[str] = []
        if source_dir.is_dir() and not source_dir.is_symlink():
            sources = sorted(
                path.name
                for path in source_dir.iterdir()
                if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
            )
        note = "notes.md" if (folder / "notes.md").is_file() else "no notes file"
        source_text = f", sources: {', '.join(sources)}" if sources else ""
        parts.append(f"{item['slug']} ({note}{source_text})")
    return "; ".join(parts)


def class_tools() -> list[dict[str, Any]]:
    path_schema = {
        "type": "string",
        "description": (
            "Path relative to the classes folder, such as biology-101/notes.md, "
            "biology-101/assignments/essay/notes.md, or biology-101/assignments/essay/sources/reading.pdf."
        ),
    }
    return [
        _tool(
            "list_class_files",
            "List classes, assignment folders, notes, and source documents.",
            {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        ),
        _tool(
            "read_class_file",
            "Read a note or source file before answering or editing. Text, PDF, and Word files return their contents. Other files return their name when the contents cannot be extracted.",
            _object({"path": path_schema}, ["path"]),
        ),
        _tool(
            "create_assignment",
            "Create an assignment folder with assignment.md, notes.md, and a sources folder for files the user adds.",
            _object(
                {
                    "class_folder": {"type": "string", "description": "Class folder name, such as biology-101."},
                    "title": {"type": "string", "description": "Assignment title."},
                    "due": {"type": "string", "description": "Due date, or an empty string if it is unknown."},
                },
                ["class_folder", "title", "due"],
            ),
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
            "delete_folder",
            "Delete a class folder or an assignment folder, including its notes and source files. Use this only when the user explicitly asks to remove that folder.",
            _object(
                {
                    "path": {
                        "type": "string",
                        "description": (
                            "Folder path relative to the classes folder, such as biology-101 "
                            "or biology-101/assignments/essay."
                        ),
                    }
                },
                ["path"],
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
            if name == "create_assignment":
                folder = add_assignment(
                    self.root,
                    str(payload.get("class_folder", "")),
                    str(payload.get("title", "")),
                    str(payload.get("due", "")),
                )
                stored = _relative(self.root, folder)
                self._mark(stored + "/notes.md")
                return f"Created {stored}."
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
            if name == "delete_folder":
                return self._delete_folder(str(payload.get("path", "")))
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
        return read_document(path)

    def _write(self, relative: str, content: str) -> str:
        path = resolve_class_file(self.root, relative)
        _require_note_file(path)
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
        _require_note_file(path)
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

    def _delete_folder(self, relative: str) -> str:
        path = resolve_class_file(self.root, relative)
        root_resolved = self.root.resolve()
        if path.is_symlink():
            raise AssistantError("class_file", "That path is not allowed in the classes folder.")
        if not path.exists():
            return "That folder does not exist."
        if not path.is_dir():
            raise AssistantError("class_file", "That path is not a folder.")
        resolved = path.resolve()
        if resolved == root_resolved or root_resolved not in resolved.parents:
            raise AssistantError("class_file", "That path is outside the classes folder.")
        stored = _relative(self.root, path)
        _remove_tree(path)
        self._mark(stored)
        return f"Deleted {stored}."

    def _search(self, query: str) -> str:
        needle = query.strip()
        if len(needle) < 2:
            return "The search needs at least two characters."
        folded = needle.casefold()
        hits: list[str] = []
        for path in _readable_files(self.root):
            try:
                lines = read_document(path).splitlines()
            except (OSError, AssistantError):
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
    if len(parts) > 5:
        raise AssistantError("class_file", "Class files can be nested at most five levels deep.")

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


def read_document(path: Path) -> str:
    """Return the text of a note, PDF, or Word file."""
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _pdf_text(path)
    elif suffix in {".doc", ".docx"}:
        text = _word_text(path)
    else:
        text = _plain_or_notice(path)
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[truncated]"
    return text


def _require_note_file(path: Path) -> None:
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        raise AssistantError(
            "class_file",
            "Notes must be a text file such as notes.md. Other files are added from the Classes window.",
        )


def _plain_or_notice(path: Path) -> str:
    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return f"Attached file {path.name} could not be read."
    if b"\x00" in sample:
        return (
            f"Attached file {path.name} ({path.stat().st_size} bytes). "
            "It is not a text document, so its contents were not extracted."
        )
    return path.read_text(encoding="utf-8", errors="replace")


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "This PDF could not be read because the PDF reader is not installed. Run scripts/install.sh."
    try:
        reader = PdfReader(str(path))
        pages = reader.pages[:40]
    except Exception:
        return "This PDF could not be read."
    parts: list[str] = []
    for index, page in enumerate(pages, start=1):
        extracted = (page.extract_text() or "").strip()
        if extracted:
            parts.append(f"--- page {index} ---\n{extracted}")
    return "\n\n".join(parts) if parts else "This PDF has no extractable text."


def _word_text(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["/usr/bin/textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "This Word document could not be read."
    if completed.returncode != 0:
        return "This Word document could not be read."
    text = (completed.stdout or "").strip()
    return text or "This Word document has no extractable text."


def _remove_tree(path: Path) -> None:
    """Delete a real directory. Symlinks are removed without following them."""
    for child in list(path.iterdir()):
        if child.is_symlink() or not child.is_dir():
            child.unlink()
            continue
        _remove_tree(child)
    path.rmdir()


def _readable_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
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
