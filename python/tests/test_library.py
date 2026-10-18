from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from assistant.classes import add_assignment, add_course
from assistant.library import start_library


def _request(url: str, data: bytes | None = None, content_type: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=data)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


class LibraryPageTests(unittest.TestCase):
    def test_pages_list_classes_assignments_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "Biology 101")
            notes = root / "biology-101" / "assignments"
            folder = add_assignment(root, "biology-101", "Lab report", due="Friday")
            (folder / "notes.md").write_text("# Notes — Lab report\n\nDiffusion across a membrane.\n", encoding="utf-8")
            server = start_library(root)
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            base = f"http://127.0.0.1:{server.server_address[1]}"

            status, home = _request(base + "/")
            self.assertEqual(status, 200)
            self.assertIn("Biology 101", home)
            self.assertIn("1 assignment", home)
            self.assertIn('setData("text/plain"', home)

            status, course = _request(base + "/class/biology-101")
            self.assertEqual(status, 200)
            self.assertIn("Lab report", course)
            self.assertIn("Due Friday", course)
            self.assertIn("/class/biology-101/notes", course)

            status, notes_page = _request(base + "/class/biology-101/notes")
            self.assertEqual(status, 200)
            self.assertIn("Diffusion across a membrane.", notes_page)

            status, assignment = _request(base + "/class/biology-101/assignments/lab-report")
            self.assertEqual(status, 200)
            self.assertIn("Diffusion across a membrane.", assignment)
            self.assertIn("Add file", assignment)
            self.assertIn('setData("text/plain"', assignment)
            self.assertNotIn("accept=", assignment)
            self.assertNotIn(str(notes), assignment)

            boundary = "----jarvis"
            payload = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="source"; filename="reading.pdf"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode() + b"%PDF-1.4 demo\n" + f"\r\n--{boundary}--\r\n".encode()
            upload = urllib.request.Request(
                base + "/class/biology-101/assignments/lab-report/sources",
                data=payload,
                method="POST",
            )
            upload.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            with urllib.request.urlopen(upload, timeout=2) as response:
                self.assertEqual(response.status, 200)
                uploaded = response.read().decode("utf-8")
            self.assertIn("reading.pdf", uploaded)
            self.assertTrue((folder / "sources" / "reading.pdf").is_file())

            with urllib.request.urlopen(base + "/class/biology-101/assignments/lab-report/sources/reading.pdf", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"%PDF-1.4 demo\n")

            status, course = _request(base + "/class/biology-101")
            self.assertEqual(status, 200)
            self.assertIn("Class files", course)
            self.assertIn("not for one assignment", course)

            class_payload = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="source"; filename="../syllabus.pdf"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode() + b"%PDF syllabus\n" + f"\r\n--{boundary}--\r\n".encode()
            class_upload = urllib.request.Request(
                base + "/class/biology-101/files",
                data=class_payload,
                method="POST",
            )
            class_upload.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            with urllib.request.urlopen(class_upload, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("syllabus.pdf", response.read().decode("utf-8"))
            stored = root / "biology-101" / "files" / "syllabus.pdf"
            self.assertTrue(stored.is_file())
            self.assertFalse((folder / "sources" / "syllabus.pdf").exists())
            with urllib.request.urlopen(base + "/class/biology-101/files/syllabus.pdf", timeout=2) as response:
                self.assertEqual(response.read(), b"%PDF syllabus\n")

            status, missing = _request(base + "/class/not-a-class")
            self.assertEqual(status, 404)
            self.assertIn("not in the classes folder", missing)

    def test_my_writing_is_added_by_the_user_and_is_not_a_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            classes = workspace / "classes"
            classes.mkdir()
            server = start_library(classes)
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            base = f"http://127.0.0.1:{server.server_address[1]}"

            status, home = _request(base + "/")
            self.assertEqual(status, 200)
            self.assertIn("My writing", home)
            self.assertIn("Not a class", home)

            status, empty = _request(base + "/writing")
            self.assertEqual(status, 200)
            self.assertIn("Jarvis cannot add to it.", empty)
            self.assertIn("Paste your writing", empty)

            payload = urllib.parse.urlencode(
                {"title": "The lake", "text": "The water was flat and bright."}
            ).encode()
            status, page = _request(base + "/writing", payload, "application/x-www-form-urlencoded")
            self.assertEqual(status, 200)
            self.assertIn("The water was flat and bright.", page)
            saved = workspace / "writing" / "my-writing.md"
            self.assertTrue(saved.is_file())
            self.assertFalse((classes / "my-writing.md").exists())
            self.assertNotIn("my-writing.md", _request(base + "/")[1])
            self.assertIn("Delete all writing", page)
            self.assertIn("This cannot be undone.", page)

            status, cleared = _request(base + "/writing/clear", b"", "application/x-www-form-urlencoded")
            self.assertEqual(status, 200)
            self.assertIn("No writing yet.", cleared)
            self.assertNotIn("The water was flat and bright.", cleared)
            self.assertNotIn("Delete all writing", cleared)
            self.assertEqual(saved.read_text(encoding="utf-8").count("\n## "), 0)


if __name__ == "__main__":
    unittest.main()
