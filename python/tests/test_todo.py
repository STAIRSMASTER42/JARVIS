from __future__ import annotations

import tempfile
import unittest
import urllib.request
from datetime import date
from pathlib import Path

from assistant.classes import add_assignment, add_course
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


if __name__ == "__main__":
    unittest.main()
