from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.errors import AssistantError
from assistant.images import prepare_image, sips_command

# 1x1 transparent PNG.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ImageTests(unittest.TestCase):
    def test_sips_command_caps_edge_and_quality(self) -> None:
        command = sips_command(Path("/tmp/in.png"), Path("/tmp/out.jpg"), 1600, 80)
        self.assertEqual(command[0], "/usr/bin/sips")
        self.assertIn("1600", command)
        self.assertIn("80", command)
        self.assertIn("--resampleHeightWidthMax", command)
        self.assertEqual(command[-1], "/tmp/out.jpg")

    def test_missing_file(self) -> None:
        with self.assertRaises(AssistantError) as caught:
            prepare_image(Path("/tmp/mac-ai-assistant-does-not-exist.png"), 1600, 80)
        self.assertEqual(caught.exception.code, "image_error")

    def test_empty_capture_is_a_permission_error_and_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shot.png"
            path.write_bytes(b"tiny")
            with self.assertRaises(AssistantError) as caught:
                prepare_image(path, 1600, 80)
            self.assertEqual(caught.exception.code, "screenshot_permission")
            self.assertFalse(path.exists())

    def test_sips_failure_deletes_the_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shot.png"
            path.write_bytes(TINY_PNG)

            def runner(*args, **kwargs):
                return _Completed(1, stderr="sips failed sk-testsecretvalue123")

            with self.assertRaises(AssistantError) as caught:
                prepare_image(path, 1600, 80, runner=runner)
            self.assertEqual(caught.exception.code, "image_error")
            self.assertNotIn("sk-testsecretvalue123", caught.exception.message)
            self.assertFalse(path.exists())

    def test_live_sips_resize_deletes_files(self) -> None:
        sips = Path("/usr/bin/sips")
        if not sips.is_file():
            self.skipTest("sips is not available")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shot.png"
            path.write_bytes(TINY_PNG)
            data, mime = prepare_image(path, 1600, 80)
            self.assertEqual(mime, "image/jpeg")
            self.assertTrue(data.startswith(b"\xff\xd8\xff"))
            self.assertFalse(path.exists())
            self.assertFalse(Path(directory).joinpath("shot-send.jpg").exists())


if __name__ == "__main__":
    unittest.main()
