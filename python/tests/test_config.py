from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assistant.config import DEFAULTS, SYSTEM_INSTRUCTION, load_config, merge_dict
from assistant.errors import AssistantError


ROOT = Path(__file__).resolve().parents[2]


class ConfigTests(unittest.TestCase):
    def test_example_config_matches_defaults(self) -> None:
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example["model"], DEFAULTS["model"])
        self.assertEqual(example["shortcut"], DEFAULTS["shortcut"])
        self.assertEqual(example["system_instruction"], SYSTEM_INSTRUCTION)
        loaded = load_config(ROOT / "config.example.json")
        self.assertEqual(loaded["max_output_tokens"], 800)
        self.assertEqual(loaded["image_detail"], "high")
        self.assertEqual(loaded["popup"]["width"], 400)
        self.assertTrue(loaded["classes_enabled"])
        self.assertEqual(loaded["classes_dir"], "")

    def test_missing_file_uses_defaults(self) -> None:
        missing = Path(tempfile.gettempdir()) / "mac-ai-assistant-missing-config.json"
        if missing.exists():
            missing.unlink()
        loaded = load_config(missing)
        self.assertEqual(loaded["model"], DEFAULTS["model"])
        self.assertEqual(loaded["shortcut"]["key"], "]")

    def test_partial_config_merges_popup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"model": "gpt-4.1-mini", "popup": {"width": 360}}), encoding="utf-8")
            loaded = load_config(path)
        self.assertEqual(loaded["model"], "gpt-4.1-mini")
        self.assertEqual(loaded["popup"]["width"], 360)
        self.assertEqual(loaded["popup"]["max_height"], DEFAULTS["popup"]["max_height"])

    def test_invalid_shortcut_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"shortcut": {"modifiers": ["ctrl"], "key": "bad key"}}), encoding="utf-8")
            with self.assertRaises(AssistantError) as caught:
                load_config(path)
        self.assertEqual(caught.exception.code, "config_error")

    def test_invalid_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(AssistantError) as caught:
                load_config(path)
        self.assertEqual(caught.exception.code, "config_error")

    def test_home_directory_cannot_be_the_classes_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"classes_dir": str(Path.home())}), encoding="utf-8")
            with self.assertRaises(AssistantError) as caught:
                load_config(path)
        self.assertEqual(caught.exception.code, "config_error")

    def test_merge_dict_nests(self) -> None:
        merged = merge_dict({"popup": {"width": 1, "margin": 2}}, {"popup": {"width": 3}})
        self.assertEqual(merged["popup"], {"width": 3, "margin": 2})


if __name__ == "__main__":
    unittest.main()
