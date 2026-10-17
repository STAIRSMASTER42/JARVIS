from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assistant.classes import ClassWorkspace, catalog
from assistant.cli import _local_context
from assistant.errors import AssistantError
from assistant.writing import add_writing, like_me_prompt, read_my_writing, writing_file, writing_tools


class WritingFileTests(unittest.TestCase):
    def test_user_writing_stays_outside_the_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            classes = workspace / "classes"
            classes.mkdir()
            saved = add_writing(classes, "The lake", "The water was flat and bright.")
            self.assertEqual(saved.resolve(), (workspace / "writing" / "my-writing.md").resolve())
            self.assertFalse((classes / "my-writing.md").exists())
            self.assertFalse((classes / "writing").exists())
            self.assertNotIn("my-writing", catalog(classes))
            self.assertIn("The water was flat and bright.", read_my_writing(classes))

            add_writing(classes, "The kitchen", "I left the light on.")
            text = saved.read_text(encoding="utf-8")
            self.assertEqual(text.count("\n## "), 2)
            self.assertIn("I left the light on.", text)

            context = ClassWorkspace(classes)
            instructions, tools, execute = _local_context({"system_instruction": "Be Jarvis."}, context)
            names = [tool["name"] for tool in tools or []]
            self.assertIn("read_my_writing", names)
            self.assertNotIn("write_my_writing", names)
            self.assertIn("You cannot create, edit, or delete that file.", instructions)
            self.assertIn("The water was flat and bright.", execute("read_my_writing", "{}"))
            refused = execute(
                "write_class_file",
                json.dumps({"path": "../writing/my-writing.md", "content": "Jarvis wrote this."}),
            )
            self.assertIn("not allowed", refused)
            self.assertNotIn("Jarvis wrote this.", saved.read_text(encoding="utf-8"))

            outside = workspace / "secret.txt"
            outside.write_text("keep", encoding="utf-8")
            linked = writing_file(classes)
            linked.unlink()
            linked.symlink_to(outside)
            with self.assertRaises(AssistantError):
                add_writing(classes, "Nope", "This should not land in the secret file.")
            self.assertEqual(outside.read_text(encoding="utf-8"), "keep")

    def test_empty_writing_is_not_a_tool_the_model_can_fill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classes = Path(directory) / "classes"
            classes.mkdir()
            self.assertIn("cannot add it", read_my_writing(classes))
            self.assertEqual([tool["name"] for tool in writing_tools()], ["read_my_writing"])
            with self.assertRaises(AssistantError):
                add_writing(classes, "   ", "words")
            with self.assertRaises(AssistantError):
                add_writing(classes, "Title", "   ")

    def test_my_writing_can_fill_most_of_the_context_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classes = Path(directory) / "classes"
            classes.mkdir()
            saved = add_writing(classes, "A long piece", "a" * 1_200_000)
            self.assertGreater(saved.stat().st_size, 1_200_000)
            with self.assertRaises(AssistantError):
                add_writing(classes, "Too big", "b" * 4_000_001)

    def test_write_like_me_puts_the_file_in_the_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classes = Path(directory) / "classes"
            classes.mkdir()
            with self.assertRaises(AssistantError):
                like_me_prompt(classes, "Explain the census.")
            add_writing(classes, "The lake", "The water was flat and bright.")
            prompt = like_me_prompt(classes, "Explain the census.")
            self.assertTrue(prompt.startswith("Explain the census."))
            self.assertIn("only words found in that text", prompt)
            self.assertIn("may add a couple of words", prompt)
            self.assertIn("Including but not limited to", prompt)
            self.assertIn("one comparison to lawn keeping", prompt)
            self.assertIn("---essay---", prompt)
            self.assertIn("---end---", prompt)
            self.assertIn("The water was flat and bright.", prompt)


if __name__ == "__main__":
    unittest.main()
