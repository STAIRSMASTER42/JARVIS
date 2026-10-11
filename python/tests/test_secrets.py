from __future__ import annotations

import subprocess
import unittest

from assistant.errors import AssistantError
from assistant.secrets import command_mentions_key, keychain_command, resolve_api_key


class _Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class SecretTests(unittest.TestCase):
    def test_environment_wins_and_keychain_is_not_called(self) -> None:
        calls: list[list[str]] = []

        def runner(*args, **kwargs):
            calls.append(list(args[0]))
            return _Result(0, "from-keychain")

        key = resolve_api_key(env={"OPENAI_API_KEY": "env-key"}, runner=runner)
        self.assertEqual(key, "env-key")
        self.assertEqual(calls, [])

    def test_keychain_command_shape(self) -> None:
        command = keychain_command()
        self.assertEqual(command[0], "/usr/bin/security")
        self.assertIn("find-generic-password", command)
        self.assertIn("mac-ai-assistant-openai", command)
        self.assertIn("charliebaker", command)
        self.assertNotIn("-w", command[:-1])
        self.assertEqual(command[-1], "-w")

    def test_keychain_value_is_returned(self) -> None:
        def runner(*args, **kwargs):
            return _Result(0, "keychain-key\n")

        self.assertEqual(resolve_api_key(env={}, runner=runner), "keychain-key")

    def test_missing_keychain_item(self) -> None:
        def runner(*args, **kwargs):
            return _Result(44, "", "item not found")

        with self.assertRaises(AssistantError) as caught:
            resolve_api_key(env={"OPENAI_API_KEY": "  "}, runner=runner)
        self.assertEqual(caught.exception.code, "missing_api_key")
        self.assertNotIn("item not found", caught.exception.message)

    def test_key_is_not_part_of_the_lookup_command(self) -> None:
        secret = "super-secret-value"
        self.assertFalse(command_mentions_key(keychain_command(), secret))

    def test_timeout_becomes_missing_key(self) -> None:
        def runner(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="security", timeout=5)

        with self.assertRaises(AssistantError) as caught:
            resolve_api_key(env={}, runner=runner)
        self.assertEqual(caught.exception.code, "missing_api_key")


if __name__ == "__main__":
    unittest.main()
