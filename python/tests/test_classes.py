from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assistant.classes import (
    ClassWorkspace,
    add_course,
    append_change_note,
    catalog,
    resolve_class_file,
    resolved_classes_dir,
    slugify,
    with_class_context,
)
from assistant.errors import AssistantError


class ClassFileTests(unittest.TestCase):
    def test_add_course_creates_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = add_course(root, "Biology 101", term="Fall 2026", instructor="Ada")
            self.assertEqual(folder.name, "biology-101")
            course = (folder / "course.md").read_text(encoding="utf-8")
            self.assertIn("# Biology 101", course)
            self.assertIn("Term: Fall 2026", course)
            self.assertIn("Instructor: Ada", course)
            self.assertTrue((folder / "notes.md").is_file())
            self.assertTrue((folder / "assignments.md").is_file())
            self.assertIn("biology-101: Biology 101", catalog(root))

    def test_slug_rejects_blank_title(self) -> None:
        with self.assertRaises(AssistantError):
            slugify("   ")

    def test_write_edit_and_search_stay_inside_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = ClassWorkspace(Path(directory))
            created = workspace.dispatch(
                "write_class_file",
                json.dumps({"path": "history-10/notes.md", "content": "The treaty was signed in 1919.\n"}),
            )
            self.assertIn("Wrote history-10/notes.md", created)
            updated = workspace.dispatch(
                "edit_class_file",
                json.dumps(
                    {
                        "path": "history-10/notes.md",
                        "old_text": "1919",
                        "new_text": "1919, in Versailles",
                    }
                ),
            )
            self.assertIn("Updated history-10/notes.md", updated)
            found = workspace.dispatch("search_class_files", json.dumps({"query": "Versailles"}))
            self.assertIn("history-10/notes.md:1:", found)
            self.assertEqual(workspace.changed, ["history-10/notes.md"])

    def test_edit_requires_one_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = ClassWorkspace(Path(directory))
            workspace.dispatch(
                "write_class_file",
                {"path": "bio/notes.md", "content": "cell cell\n"},
            )
            message = workspace.dispatch(
                "edit_class_file",
                {"path": "bio/notes.md", "old_text": "cell", "new_text": "neuron"},
            )
            self.assertIn("appears 2 times", message)
            self.assertIn("cell cell", (Path(directory) / "bio" / "notes.md").read_text(encoding="utf-8"))

    def test_paths_outside_the_folder_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            for relative in ("../secrets.md", "/etc/passwd", "notes.py", "bio/../../outside.md"):
                with self.assertRaises(AssistantError):
                    resolve_class_file(root, relative)

    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "classes"
            root.mkdir()
            outside = Path(directory) / "outside.md"
            outside.write_text("secret", encoding="utf-8")
            course = root / "bio"
            course.mkdir()
            (course / "notes.md").symlink_to(outside)
            with self.assertRaises(AssistantError):
                resolve_class_file(root, "bio/notes.md")

    def test_change_note_is_added_once(self) -> None:
        once = append_change_note("The answer is B.", ["bio/notes.md"])
        self.assertIn("Updated bio/notes.md.", once)
        self.assertEqual(append_change_note(once, ["bio/notes.md"]), once)

    def test_context_mentions_the_catalog(self) -> None:
        text = with_class_context("Be concise.", "Classes:\n- bio: Biology")
        self.assertTrue(text.startswith("Be concise."))
        self.assertIn("biology", text.lower())
        self.assertIn("Classes:", text)

    def test_documents_root_is_not_a_classes_folder(self) -> None:
        with self.assertRaises(AssistantError) as caught:
            resolved_classes_dir({"classes_dir": str(Path.home() / "Documents")})
        self.assertEqual(caught.exception.code, "config_error")

    def test_duplicate_class_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "Biology 101")
            with self.assertRaises(AssistantError) as caught:
                add_course(root, "Biology 101")
        self.assertIn("already exists", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
