from __future__ import annotations

import unittest
from types import SimpleNamespace

from assistant.client import (
    web_search_tool,
    build_analyze_request,
    build_connection_request,
    CONTINUE_IMAGE_PROMPT,
    analyze_prompt,
    build_continue_image_request,
    continue_image_prompt,
    build_followup_request,
    complete,
    complete_with_tools,
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
    def test_web_search_pages_are_named(self) -> None:
        response = {
            "output_text": "The due date is Friday.",
            "output": [
                {
                    "content": [
                        {
                            "text": "The due date is Friday.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Course calendar",
                                    "url": "https://example.edu/calendar",
                                    "start_index": 0,
                                    "end_index": 4,
                                }
                            ],
                        }
                    ]
                }
            ],
        }
        text = extract_text(response)
        self.assertIn("The due date is Friday.", text)
        self.assertIn("Course calendar (https://example.edu/calendar)", text)
        self.assertEqual(web_search_tool()["type"], "web_search")
        self.assertTrue(web_search_tool()["external_web_access"])

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
        self.assertEqual(payload["reasoning"], {"effort": "high"})

    def test_continue_image_keeps_previous_response(self) -> None:
        payload = build_continue_image_request(
            model="gpt-5.4-mini",
            instructions="Be concise.",
            previous_response_id="resp_123",
            prompt="Another screenshot of the same work.",
            data_url="data:image/jpeg;base64,aaaa",
            detail="high",
            max_output_tokens=800,
            tools=[{"type": "function", "name": "read_class_file"}],
        )
        self.assertEqual(payload["previous_response_id"], "resp_123")
        content = payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "high")
        self.assertEqual(payload["tools"][0]["name"], "read_class_file")
        self.assertEqual(payload["reasoning"], {"effort": "high"})

    def test_first_screenshot_prompt_includes_the_text_box(self) -> None:
        self.assertEqual(analyze_prompt("Look at this screenshot."), "Look at this screenshot.")
        prompt = analyze_prompt("Look at this screenshot.", "  Answer question 3  ")
        self.assertTrue(prompt.startswith("Answer question 3\n\n"))
        self.assertIn("Look at this screenshot.", prompt)

    def test_continue_prompt_includes_the_text_box(self) -> None:
        self.assertEqual(continue_image_prompt("  "), CONTINUE_IMAGE_PROMPT)
        prompt = continue_image_prompt("  Answer question 3  ")
        self.assertTrue(prompt.startswith("Answer question 3\n\n"))
        self.assertIn(CONTINUE_IMAGE_PROMPT, prompt)

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
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertNotIn("image_url", str(payload["input"]))

    def test_message_can_start_without_a_screenshot(self) -> None:
        payload = build_followup_request(
            model="gpt-5.4-mini",
            instructions="Be concise.",
            text="Help me study unit 1.",
            max_output_tokens=800,
        )
        self.assertNotIn("previous_response_id", payload)
        self.assertNotIn("input_image", str(payload))
        self.assertEqual(payload["input"], "Help me study unit 1.")

    def test_connection_request_has_no_image(self) -> None:
        payload = build_connection_request(model="gpt-5.4-mini")
        self.assertNotIn("input_image", str(payload))
        self.assertLessEqual(payload["max_output_tokens"], 16)
        self.assertNotIn("reasoning", payload)

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

    def test_tool_round_trip(self) -> None:
        calls: list[tuple[str, str]] = []

        class _Responses:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []

            def create(self, **kwargs: object) -> object:
                self.payloads.append(kwargs)
                if len(self.payloads) == 1:
                    return SimpleNamespace(
                        id="resp_1",
                        output_text="",
                        output=[
                            SimpleNamespace(
                                type="function_call",
                                name="read_class_file",
                                call_id="call_1",
                                arguments='{"path": "bio/notes.md"}',
                            )
                        ],
                    )
                return {"output_text": "Answer B", "id": "resp_2", "output": []}

        client = SimpleNamespace(responses=_Responses())

        def execute(name: str, arguments: str) -> str:
            calls.append((name, arguments))
            return "Chapter 3 is diffusion."

        text, identifier = complete_with_tools(
            client,
            {"model": "gpt-5.4-mini", "max_output_tokens": 800, "tools": [{"type": "function", "name": "read_class_file"}]},
            execute,
        )
        self.assertEqual(text, "Answer B")
        self.assertEqual(identifier, "resp_2")
        self.assertEqual(calls, [("read_class_file", '{"path": "bio/notes.md"}')])
        follow = client.responses.payloads[1]
        self.assertEqual(follow["previous_response_id"], "resp_1")
        self.assertEqual(follow["input"][0]["type"], "function_call_output")
        self.assertEqual(follow["input"][0]["output"], "Chapter 3 is diffusion.")

    def test_too_many_tool_rounds(self) -> None:
        class _Responses:
            def create(self, **kwargs: object) -> object:
                return SimpleNamespace(
                    id="resp_loop",
                    output_text="",
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="list_class_files",
                            call_id="call_1",
                            arguments="{}",
                        )
                    ],
                )

        with self.assertRaises(AssistantError) as caught:
            complete_with_tools(
                SimpleNamespace(responses=_Responses()),
                {"model": "gpt-5.4-mini", "max_output_tokens": 100, "tools": []},
                lambda name, arguments: "ok",
                max_rounds=1,
            )
        self.assertEqual(caught.exception.code, "bad_response")


if __name__ == "__main__":
    unittest.main()
