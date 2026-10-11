from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from assistant.config import load_config
from assistant.errors import AssistantError, sanitize
from assistant.images import prepare_image
from assistant.secrets import resolve_api_key
from assistant import client as api


def emit(payload: dict[str, Any], stream: TextIO | None = None) -> int:
    destination = stream or sys.stdout
    json.dump(payload, destination, ensure_ascii=False)
    destination.write("\n")
    destination.flush()
    return 0 if payload.get("ok") else 1


def emit_error(error: AssistantError, stream: TextIO | None = None) -> int:
    return emit(
        {"ok": False, "code": error.code, "error": sanitize(error.message)},
        stream,
    )


def _config_path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def analyze(image: Path, config_path: Path | None, keep_image: bool) -> dict[str, Any]:
    config = load_config(config_path)
    data, mime = prepare_image(
        image,
        max_edge=config["image_max_edge"],
        quality=config["jpeg_quality"],
        keep=keep_image,
    )
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    payload = api.build_analyze_request(
        model=config["model"],
        instructions=config["system_instruction"],
        prompt=config["user_prompt"],
        data_url=api.image_data_url(data, mime),
        detail=config["image_detail"],
        max_output_tokens=config["max_output_tokens"],
    )
    text, response_id = api.complete(openai_client, payload)
    return {"ok": True, "text": text, "response_id": response_id}


def followup(previous_id: str, text: str, config_path: Path | None) -> dict[str, Any]:
    if not previous_id.strip():
        raise AssistantError(
            "bad_response",
            "This answer cannot be continued. Take a new screenshot and try again.",
        )
    if not text.strip():
        raise AssistantError("bad_request", "Enter a follow-up question first.")
    config = load_config(config_path)
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    payload = api.build_followup_request(
        model=config["model"],
        instructions=config["system_instruction"],
        previous_response_id=previous_id.strip(),
        text=text.strip(),
        max_output_tokens=config["max_output_tokens"],
    )
    answer, response_id = api.complete(openai_client, payload)
    return {"ok": True, "text": answer, "response_id": response_id}


def test_connection(config_path: Path | None) -> dict[str, Any]:
    config = load_config(config_path)
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    payload = api.build_connection_request(model=config["model"])
    text, response_id = api.complete(openai_client, payload)
    return {
        "ok": True,
        "text": text,
        "response_id": response_id,
        "model": config["model"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistant",
        description="Send a screenshot or follow-up to the OpenAI Responses API.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a screenshot file")
    analyze_parser.add_argument("--image", required=True, help="Path to a temporary screenshot")
    analyze_parser.add_argument("--config", help="Path to config.json")
    analyze_parser.add_argument(
        "--keep-image",
        action="store_true",
        help="Do not delete the screenshot (debugging only)",
    )

    follow_parser = subparsers.add_parser("followup", help="Continue the current screenshot session")
    follow_parser.add_argument("--previous-id", required=True)
    follow_parser.add_argument("--text", required=True)
    follow_parser.add_argument("--config")

    test_parser = subparsers.add_parser("test-connection", help="Send a tiny text request to OpenAI")
    test_parser.add_argument("--config")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        config_path = _config_path(getattr(args, "config", None))
        if args.command == "analyze":
            payload = analyze(Path(args.image).expanduser(), config_path, args.keep_image)
        elif args.command == "followup":
            payload = followup(args.previous_id, args.text, config_path)
        elif args.command == "test-connection":
            payload = test_connection(config_path)
        else:
            raise AssistantError("bad_request", "Unknown command.")
        return emit(payload)
    except AssistantError as exc:
        return emit_error(exc)
    except Exception as exc:  # noqa: BLE001 — last-resort guard so the popup gets JSON
        message = sanitize(str(exc))[:300] or "The request failed for an unexpected reason."
        return emit({"ok": False, "code": "unexpected", "error": message})
