from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHONPATH = str(ROOT / "python")


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "assistant", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**dict(**{k: v for k, v in __import__("os").environ.items() if k != "OPENAI_API_KEY"}), "PYTHONPATH": PYTHONPATH},
    )


class CliTests(unittest.TestCase):
    def test_missing_image_is_json(self) -> None:
        completed = run_module(
            "analyze",
            "--image",
            "/tmp/mac-ai-assistant-missing.png",
            "--config",
            str(ROOT / "config.example.json"),
        )
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "image_error")
        self.assertNotIn("sk-", completed.stdout)
        self.assertEqual(completed.returncode, 1)

    def test_empty_followup_is_json(self) -> None:
        completed = run_module(
            "followup",
            "--previous-id",
            "resp_123",
            "--text",
            "   ",
            "--config",
            str(ROOT / "config.example.json"),
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["code"], "bad_request")

    def test_source_does_not_hardcode_an_api_key(self) -> None:
        needles = ("sk-proj", "sk-live", "sk-testsecret")
        for path in (ROOT / "python" / "assistant").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                self.assertNotIn(needle, text, msg=str(path))


if __name__ == "__main__":
    unittest.main()
