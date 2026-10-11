from __future__ import annotations

import unittest
from types import SimpleNamespace

from assistant.client import (
    build_analyze_request,
    build_connection_request,
    build_followup_request,
    complete,
    extract_text,
    image_data_url,
    response_id,
)
from assistant.errors import AssistantError


class _Blocks:
    def __init__(self, text: str) -> None:
        self.text = text


class _Item:
    def __init__(self, content: list[object]) -> None:
        self.content = content


class ClientTests(unittest.TestCase):
    def test_image_request_shape(self) -> None:
        payload = build_analyze_request(
            model="gpt-5.4-mini",
            instructions="Be concise.",
            prompt="Analyze this screenshot.",
            data_url="data:image/jpeg;base64,aaaa",
            detail="high",
            max_output_tokens=800,
        )
        content = payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "high")
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("file_id", content[1])

    def test_followup_keeps_previous_response(self) -> None:
        payload = build_followup_request(
            model="gpt-5.4-mini",
            instructions="Be concise.",
            previous_response_id="resp_123",
            text="Why that choice?",
            max_output_tokens=800,
        )
        self.assertEqual(payload["previous_response_id"], "resp_123")
        self.assertEqual(payload["input"], "Why that choice?")
        self.assertNotIn("image_url", str(payload["input"]))

    def test_connection_request_has_no_image(self) -> None:
        payload = build_connection_request(model="gpt-5.4-mini")
        self.assertNotIn("input_image", str(payload))
        self.assertLessEqual(payload["max_output_tokens"], 16)

    def test_data_url(self) -> None:
        url = image_data_url(b"\xff\xd8\xff", "image/jpeg")
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))

    def test_extract_output_text(self) -> None:
        self.assertEqual(extract_text({"output_text": "  Answer B  "}), "Answer B")
        self.assertEqual(extract_text(SimpleNamespace(output_text="From the object")), "From the object")

    def test_extract_walks_content_blocks(self) -> None:
        response = SimpleNamespace(
            output_text="",
            output=[_Item([_Blocks("Line one"), {"text": "Line two"}])],
            id="resp_abc",
        )
        self.assertEqual(extract_text(response), "Line one\nLine two")
        self.assertEqual(response_id(response), "resp_abc")

    def test_empty_response_is_an_error(self) -> None:
        class _Client:
            class responses:
                @staticmethod
                def create(**kwargs):
                    return {"output_text": "  ", "id": "resp_empty"}

        with self.assertRaises(AssistantError) as caught:
            complete(_Client(), {"model": "gpt-5.4-mini", "input": "hi"})
        self.assertEqual(caught.exception.code, "bad_response")

    def test_provider_exception_is_mapped(self) -> None:
        class _Boom(Exception):
            status_code = 401

        _Boom.__name__ = "AuthenticationError"

        class _Client:
            class responses:
                @staticmethod
                def create(**kwargs):
                    raise _Boom("denied")

        with self.assertRaises(AssistantError) as caught:
            complete(_Client(), {"model": "gpt-5.4-mini", "input": "hi"})
        self.assertEqual(caught.exception.code, "invalid_api_key")


if __name__ == "__main__":
    unittest.main()
