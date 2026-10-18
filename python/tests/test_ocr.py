from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.errors import AssistantError
from assistant.ocr import read_image


class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class OcrTests(unittest.TestCase):
    def test_reads_text_and_deletes_the_picture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "region.png"
            path.write_bytes(b"x" * 64)
            calls: list[list[str]] = []

            def runner(command: list[str]) -> _Completed:
                calls.append(command)
                mode = command[command.index("--psm") + 1]
                if mode == "6":
                    return _Completed(0, "Hello from the screen\n")
                return _Completed(0, "")

            text = read_image(path, runner)
            self.assertEqual(text, "Hello from the screen")
            self.assertFalse(path.exists())
            self.assertEqual(calls[0][2], "stdout")
            self.assertIn("--psm", calls[0])

    def test_sparse_text_is_tried_when_the_block_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "region.png"
            path.write_bytes(b"x" * 64)

            def runner(command: list[str]) -> _Completed:
                mode = command[command.index("--psm") + 1]
                if mode == "11":
                    return _Completed(0, "Menu item")
                return _Completed(0, "   ")

            self.assertEqual(read_image(path, runner), "Menu item")
            self.assertFalse(path.exists())

    def test_empty_capture_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.png"
            path.write_bytes(b"x")
            with self.assertRaises(AssistantError) as caught:
                read_image(path, lambda command: _Completed(0, "nope"))
            self.assertEqual(caught.exception.code, "ocr_error")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
