from __future__ import annotations

import tempfile
import unittest
import urllib.request
from datetime import date
from pathlib import Path

from assistant.classes import add_assignment, add_course, set_assignment_done
from assistant.library import start_library
from assistant.todo import collect_todos, filter_todos, parse_due


class TodoTests(unittest.TestCase):
    def test_filters_assignments_from_every_class_by_how_soon_they_are_due(self) -> None:
        today = date(2026, 10, 11)
        self.assertEqual(parse_due("2026-10-12", today), date(2026, 10, 12))
        self.assertEqual(parse_due("October 15, 2026", today), date(2026, 10, 15))
        self.assertEqual(parse_due("Oct 15", today), date(2026, 10, 15))
        self.assertIsNone(parse_due("Friday", today))
        self.assertIsNone(parse_due("unknown", today))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "Biology 101")
            add_course(root, "History")
            add_assignment(root, "biology-101", "Lab report", due="2026-10-12")
            add_assignment(root, "history", "Essay", due="2026-11-20")
            add_assignment(root, "history", "Reading", due="2026-10-01")
            add_assignment(root, "biology-101", "Notes", due="Friday")

            items = collect_todos(root, today)
            self.assertEqual([item.title for item in items], ["Reading", "Lab report", "Essay", "Notes"])

            one_day = [item.title for item in filter_todos(items, today, 1)]
            self.assertEqual(one_day, ["Reading", "Lab report"])
            week = [item.title for item in filter_todos(items, today, 7)]
            self.assertEqual(week, ["Reading", "Lab report"])
            month = [item.title for item in filter_todos(items, today, 30)]
            self.assertEqual(month, ["Reading", "Lab report"])
            quarter = [item.title for item in filter_todos(items, today, 90)]
            self.assertEqual(quarter, ["Reading", "Lab report", "Essay"])
            self.assertNotIn("Notes", quarter)

            server = start_library(root)
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/todo?days=7", timeout=2) as response:
                page = response.read().decode("utf-8")
            self.assertIn("Lab report", page)
            self.assertIn("Biology 101", page)
            self.assertIn("Reading", page)
            self.assertNotIn("Essay", page)
            self.assertIn('href="/todo?days=1"', page)
            self.assertIn('href="/todo?days=90"', page)
            self.assertIn("Overdue", page)

    def test_bold_english_due_line_is_read(self) -> None:
        today = date(2026, 10, 11)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "English")
            folder = add_assignment(root, "english", "Workshop 1", due="unknown")
            (folder / "assignment.md").write_text(
                "# Workshop 1: Everyday Arguments\n\n**Due:** 2026-10-13\n\n## Description\nPractice arguments.\n",
                encoding="utf-8",
            )
            items = collect_todos(root, today)
            self.assertEqual(items[0].due, date(2026, 10, 13))
            self.assertEqual(items[0].due_text, "2026-10-13")

    def test_done_assignments_leave_the_active_list(self) -> None:
        today = date(2026, 10, 11)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "English")
            folder = add_assignment(root, "english", "Workshop 1", due="unknown")
            (folder / "assignment.md").write_text(
                "# Workshop 1\n\n**Due:** 2026-10-13\n\n## Description\nPractice arguments.\n",
                encoding="utf-8",
            )
            set_assignment_done(root, "english", "workshop-1", True)
            text = (folder / "assignment.md").read_text(encoding="utf-8")
            self.assertIn("**Due:** 2026-10-13", text)
            self.assertIn("- Status: done", text)
            self.assertIn("## Description", text)

            items = collect_todos(root, today)
            self.assertTrue(items[0].done)
            self.assertEqual(filter_todos(items, today, 7), [])
            self.assertEqual(filter_todos(items, today, None), [])

            server = start_library(root)
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/todo", timeout=2) as response:
                page = response.read().decode("utf-8")
            self.assertIn(">Done</h2>", page)
            self.assertIn("Undo", page)
            self.assertNotIn(">Overdue</h2>", page)

            undone = urllib.request.Request(
                base + "/class/english/assignments/workshop-1/done",
                data=b"done=no&next=/todo",
                method="POST",
            )
            with urllib.request.urlopen(undone, timeout=2) as response:
                restored = response.read().decode("utf-8")
            self.assertIn("Workshop 1", restored)
            self.assertNotIn("- Status: done", (folder / "assignment.md").read_text(encoding="utf-8"))
            self.assertIn("**Due:** 2026-10-13", (folder / "assignment.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
