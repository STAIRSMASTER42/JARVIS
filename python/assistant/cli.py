from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from assistant.classes import (
    ClassWorkspace,
    add_course,
    append_change_note,
    catalog,
    class_tools,
    resolved_classes_dir,
    with_class_context,
)
from assistant.library import serve_library
from assistant.writing import WRITING_GUIDANCE, read_my_writing, writing_summary, writing_tools
from assistant.config import load_config
from assistant.errors import AssistantError, sanitize
from assistant.images import prepare_image
from assistant.secrets import resolve_api_key
from assistant import client as api

# Tool arguments, such as a notes file, need more room than a short popup answer.
CLASS_OUTPUT_TOKENS = 8000


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


def _class_workspace(config: dict[str, Any]) -> ClassWorkspace | None:
    if not config.get("classes_enabled"):
        return None
    return ClassWorkspace(resolved_classes_dir(config))


def _local_context(config: dict[str, Any], workspace: ClassWorkspace | None) -> tuple[str, list[dict[str, Any]] | None, Any]:
    instructions = config["system_instruction"]
    if workspace is None:
        return instructions, None, None
    instructions = with_class_context(instructions, catalog(workspace.root))
    instructions = instructions.rstrip() + "\n\n" + WRITING_GUIDANCE + "\n\n" + writing_summary(workspace.root) + "\n"
    tools = class_tools() + writing_tools()

    def execute(name: str, arguments: str) -> str:
        if name == "read_my_writing":
            return read_my_writing(workspace.root)
        return workspace.dispatch(name, arguments)

    return instructions, tools, execute


def _finish(text: str, response_id: str, workspace: ClassWorkspace | None) -> dict[str, Any]:
    if workspace is not None:
        text = append_change_note(text, workspace.changed)
    return {"ok": True, "text": text, "response_id": response_id}


def analyze(
    image: Path,
    config_path: Path | None,
    keep_image: bool,
    previous_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    config = load_config(config_path)
    data, mime = prepare_image(
        image,
        max_edge=config["image_max_edge"],
        quality=config["jpeg_quality"],
        keep=keep_image,
    )
    workspace = _class_workspace(config)
    instructions, tools, execute = _local_context(config, workspace)
    output_tokens = config["max_output_tokens"]
    if workspace is not None:
        output_tokens = max(output_tokens, CLASS_OUTPUT_TOKENS)
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    data_url = api.image_data_url(data, mime)
    continued = (previous_id or "").strip()
    if continued:
        payload = api.build_continue_image_request(
            model=config["model"],
            instructions=instructions,
            previous_response_id=continued,
            prompt=api.continue_image_prompt(note),
            data_url=data_url,
            detail=config["image_detail"],
            max_output_tokens=output_tokens,
            tools=tools,
        )
    else:
        payload = api.build_analyze_request(
            model=config["model"],
            instructions=instructions,
            prompt=api.analyze_prompt(config["user_prompt"], note),
            data_url=data_url,
            detail=config["image_detail"],
            max_output_tokens=output_tokens,
            tools=tools,
        )
    if workspace is None:
        text, response_id = api.complete(openai_client, payload)
    else:
        text, response_id = api.complete_with_tools(openai_client, payload, execute)
    return _finish(text, response_id, workspace)


def followup(previous_id: str, text: str, config_path: Path | None) -> dict[str, Any]:
    if not previous_id.strip():
        raise AssistantError(
            "bad_response",
            "This answer cannot be continued. Take a new screenshot and try again.",
        )
    if not text.strip():
        raise AssistantError("bad_request", "Enter a follow-up question first.")
    config = load_config(config_path)
    workspace = _class_workspace(config)
    instructions, tools, execute = _local_context(config, workspace)
    output_tokens = config["max_output_tokens"]
    if workspace is not None:
        output_tokens = max(output_tokens, CLASS_OUTPUT_TOKENS)
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    payload = api.build_followup_request(
        model=config["model"],
        instructions=instructions,
        previous_response_id=previous_id.strip(),
        text=text.strip(),
        max_output_tokens=output_tokens,
        tools=tools,
    )
    if workspace is None:
        answer, response_id = api.complete(openai_client, payload)
    else:
        answer, response_id = api.complete_with_tools(openai_client, payload, execute)
    return _finish(answer, response_id, workspace)


def test_connection(config_path: Path | None, model: str | None = None) -> dict[str, Any]:
    config = load_config(config_path)
    chosen_model = (model or config["model"]).strip()
    if not chosen_model or any(char.isspace() for char in chosen_model):
        raise AssistantError("config_error", "The connectivity test needs a model name.")
    api_key = resolve_api_key()
    openai_client = api.make_client(api_key, config["timeout_seconds"])
    payload = api.build_connection_request(model=chosen_model)
    text, response_id = api.complete(openai_client, payload)
    return {
        "ok": True,
        "text": text,
        "response_id": response_id,
        "model": chosen_model,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistant",
        description="Send a screenshot or follow-up to the OpenAI Responses API.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a screenshot file")
    analyze_parser.add_argument("--image", required=True, help="Path to a temporary screenshot")
    analyze_parser.add_argument(
        "--previous-id",
        default="",
        help="Continue this response with another screenshot",
    )
    analyze_parser.add_argument(
        "--text",
        default="",
        help="Text from the popup to include with another screenshot",
    )
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
    test_parser.add_argument(
        "--model",
        default="gpt-5.4-nano",
        help="Low-cost model used for the connectivity check",
    )

    classes_parser = subparsers.add_parser("classes", help="Create and list local class folders")
    classes_parser.add_argument("--config")
    classes_sub = classes_parser.add_subparsers(dest="classes_command", required=True)
    classes_sub.add_parser("path", help="Print the classes folder")
    classes_sub.add_parser("list", help="List class folders")
    classes_sub.add_parser("serve", help="Open the classes page on this Mac")
    add_parser = classes_sub.add_parser("add", help="Create a class folder")
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--term", default="")
    add_parser.add_argument("--instructor", default="")
    add_parser.add_argument("--schedule", default="")
    return parser


def run_classes(args: argparse.Namespace) -> int:
    config = load_config(_config_path(getattr(args, "config", None)))
    root = resolved_classes_dir(config)
    if args.classes_command == "path":
        print(root)
        return 0
    if args.classes_command == "list":
        workspace = ClassWorkspace(root)
        print(catalog(workspace.root))
        return 0
    if args.classes_command == "serve":
        serve_library(root)
        return 0
    if args.classes_command == "add":
        folder = add_course(
            root,
            args.title,
            term=args.term,
            instructor=args.instructor,
            schedule=args.schedule,
        )
        print(folder)
        return 0
    raise AssistantError("bad_request", "Unknown classes command.")


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        config_path = _config_path(getattr(args, "config", None))
        if args.command == "analyze":
            payload = analyze(
                Path(args.image).expanduser(),
                config_path,
                args.keep_image,
                args.previous_id,
                args.text,
            )
        elif args.command == "followup":
            payload = followup(args.previous_id, args.text, config_path)
        elif args.command == "test-connection":
            payload = test_connection(config_path, args.model)
        elif args.command == "classes":
            try:
                return run_classes(args)
            except AssistantError as exc:
                sys.stderr.write(exc.message + "\n")
                return 1
        else:
            raise AssistantError("bad_request", "Unknown command.")
        return emit(payload)
    except AssistantError as exc:
        return emit_error(exc)
    except Exception as exc:  # noqa: BLE001 — last-resort guard so the popup gets JSON
        message = sanitize(str(exc))[:300] or "The request failed for an unexpected reason."
        return emit({"ok": False, "code": "unexpected", "error": message})
