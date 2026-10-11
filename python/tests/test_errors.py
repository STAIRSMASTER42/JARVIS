from __future__ import annotations

import unittest

from assistant.errors import AssistantError, map_exception, sanitize


def named_error(class_name: str, message: str, status_code: int | None = None, body: dict | None = None) -> Exception:
    error_type = type(class_name, (Exception,), {})
    error = error_type(message)
    error.status_code = status_code
    error.body = body
    return error


class ErrorTests(unittest.TestCase):
    def test_sanitize_redacts_key_and_bearer_token(self) -> None:
        raw = "failed for sk-testsecretvalue123 and Bearer abcdefghijklmnop"
        cleaned = sanitize(raw)
        self.assertNotIn("sk-testsecretvalue123", cleaned)
        self.assertNotIn("abcdefghijklmnop", cleaned)
        self.assertIn("[redacted]", cleaned)

    def test_authentication_error(self) -> None:
        error = named_error("AuthenticationError", "AuthenticationError: bad key sk-testsecretvalue123")
        mapped = map_exception(error)
        self.assertEqual(mapped.code, "invalid_api_key")
        self.assertNotIn("sk-", mapped.message)

    def test_quota_from_status_and_body(self) -> None:
        error = named_error(
            "RateLimitError",
            "nope",
            status_code=429,
            body={"error": {"code": "insufficient_quota"}},
        )
        mapped = map_exception(error)
        self.assertEqual(mapped.code, "quota")

    def test_billing_status(self) -> None:
        error = named_error("APIStatusError", "payment required", status_code=402)
        mapped = map_exception(error)
        self.assertEqual(mapped.code, "quota")

    def test_timeout_and_network(self) -> None:
        timeout = named_error("APITimeoutError", "request timed out")
        offline = named_error("APIConnectionError", "connection error")
        self.assertEqual(map_exception(timeout).code, "timeout")
        self.assertEqual(map_exception(offline).code, "network")

    def test_bad_request_includes_sanitized_detail(self) -> None:
        error = named_error("BadRequestError", "model missing sk-testsecretvalue123", status_code=400)
        mapped = map_exception(error)
        self.assertEqual(mapped.code, "bad_request")
        self.assertNotIn("sk-testsecretvalue123", mapped.message)

    def test_assistant_error_passes_through(self) -> None:
        original = AssistantError("image_error", "nope")
        self.assertIs(map_exception(original), original)


if __name__ == "__main__":
    unittest.main()
