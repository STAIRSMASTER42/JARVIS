"""Practice tests stored beside a class, in the practice-tester question format."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from assistant.classes import _course_dir, slugify
from assistant.errors import AssistantError

_MAX_CHARS = 120_000
_KEYS = ("ID", "TYPE", "PROMPT", "CHOICES", "ANSWER", "EXPLANATION", "TAGS")
_KEY_SPLIT = re.compile(r"\n\s*(ID|TYPE|PROMPT|CHOICES|ANSWER|EXPLANATION|TAGS)\s*:")
_CHOICE_LINE = re.compile(r"^([A-Z])\)\s*(.+)$")
_TF_CHOICES = (("A", "TRUE"), ("B", "FALSE"))


@dataclass(frozen=True)
class Question:
    id: str
    type: str
    prompt: str
    choices: tuple[tuple[str, str], ...]
    answers: frozenset[str]
    explanation: str
    tags: tuple[str, ...]
    source: str

    def is_correct(self, selected: set[str]) -> bool:
        return self.answers == frozenset(selected)


def practice_dir(root: Path, class_folder: str) -> Path:
    course = _course_dir(root, class_folder)
    folder = course / "practice-tests"
    if folder.is_symlink():
        raise AssistantError("class_file", "That practice-test folder is not allowed.")
    return folder


def list_practice_tests(root: Path, class_folder: str) -> list[dict[str, str | int]]:
    folder = practice_dir(root, class_folder)
    if not folder.is_dir():
        return []
    found: list[dict[str, str | int]] = []
    for path in sorted((item for item in folder.iterdir() if item.is_dir() and not item.is_symlink()), key=lambda item: item.name):
        questions_path = path / "questions.txt"
        if questions_path.is_symlink() or not questions_path.is_file():
            continue
        try:
            count = len(parse_questions(questions_path.read_text(encoding="utf-8", errors="replace")))
        except AssistantError:
            count = 0
        title_path = path / "title.txt"
        title = path.name
        if title_path.is_file() and not title_path.is_symlink():
            stored = title_path.read_text(encoding="utf-8", errors="replace").strip()
            if stored:
                title = stored.splitlines()[0].strip() or title
        review = path / "review.txt"
        review_count = 0
        if review.is_file() and not review.is_symlink():
            try:
                review_count = len(parse_questions(review.read_text(encoding="utf-8", errors="replace")))
            except AssistantError:
                review_count = 0
        found.append({"slug": path.name, "title": title, "count": count, "review_count": review_count})
    return found


def save_practice_test(root: Path, class_folder: str, title: str, questions: str) -> tuple[Path, int, bool]:
    """Write one practice test. Returns the questions file, the question count, and whether it replaced an existing test."""
    cleaned_title = " ".join(title.split())
    if not cleaned_title:
        raise AssistantError("class_file", "A practice test needs a title, such as Unit 1 or Midterm.")
    if len(cleaned_title) > 120:
        raise AssistantError("class_file", "That practice test title is too long.")
    text = questions.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise AssistantError("class_file", "A practice test needs at least one question.")
    if len(text) > _MAX_CHARS:
        raise AssistantError("class_file", "That practice test is too long to save in one step.")
    parsed = parse_questions(text)
    folder_root = practice_dir(root, class_folder)
    folder_root.mkdir(exist_ok=True)
    slug = slugify(cleaned_title)
    folder = folder_root / slug
    if folder.is_symlink():
        raise AssistantError("class_file", "That practice-test folder is not allowed.")
    replaced = (folder / "questions.txt").is_file()
    folder.mkdir(exist_ok=True)
    questions_path = folder / "questions.txt"
    title_path = folder / "title.txt"
    if questions_path.is_symlink() or title_path.is_symlink():
        raise AssistantError("class_file", "That practice-test file is not allowed.")
    questions_path.write_text(text + "\n", encoding="utf-8")
    title_path.write_text(cleaned_title + "\n", encoding="utf-8")
    return questions_path, len(parsed), replaced


def load_questions(root: Path, class_folder: str, test_folder: str, *, review: bool = False) -> tuple[str, list[Question]]:
    folder = _test_dir(root, class_folder, test_folder)
    path = folder / ("review.txt" if review else "questions.txt")
    if path.is_symlink() or not path.is_file():
        if review:
            raise AssistantError("class_file", "No questions are marked for review.")
        raise AssistantError("class_file", "That practice test does not exist.")
    questions = parse_questions(path.read_text(encoding="utf-8", errors="replace"))
    title = test_folder
    title_path = folder / "title.txt"
    if title_path.is_file() and not title_path.is_symlink():
        stored = title_path.read_text(encoding="utf-8", errors="replace").strip()
        if stored:
            title = stored.splitlines()[0].strip() or title
    if review:
        title = f"Review — {title}"
    return title, questions


def grade_answer(question: Question, selected: list[str]) -> bool:
    labels = {str(item).strip().upper() for item in selected if str(item).strip()}
    return question.is_correct(labels)


def mark_for_review(root: Path, class_folder: str, test_folder: str, question: Question) -> None:
    folder = _test_dir(root, class_folder, test_folder)
    path = folder / "review.txt"
    if path.is_symlink():
        raise AssistantError("class_file", "That review file is not allowed.")
    current = ""
    if path.is_file():
        current = path.read_text(encoding="utf-8", errors="replace")
        try:
            existing = {item.id for item in parse_questions(current)}
        except AssistantError:
            existing = set()
        if question.id in existing:
            return
    addition = question.source.strip() + "\n"
    updated = (current.rstrip() + "\n\n" + addition).strip() + "\n" if current.strip() else addition
    path.write_text(updated, encoding="utf-8")


def question_by_id(questions: list[Question], question_id: str) -> Question:
    for question in questions:
        if question.id == question_id:
            return question
    raise AssistantError("class_file", "That question is not in this practice test.")


def public_questions(questions: list[Question]) -> list[dict[str, object]]:
    """Question text for the quiz page. Answers stay on the server until the question is submitted."""
    return [
        {
            "id": question.id,
            "type": question.type,
            "prompt": question.prompt,
            "choices": [{"label": label, "text": text} for label, text in question.choices],
        }
        for question in questions
    ]


def parse_questions(content: str) -> list[Question]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content.replace("\r\n", "\n").replace("\r", "\n")) if block.strip()]
    if not blocks:
        raise AssistantError("class_file", "A practice test needs at least one question.")
    questions: list[Question] = []
    seen: set[str] = set()
    for index, block in enumerate(blocks, start=1):
        try:
            question = _parse_block(block)
        except AssistantError as exc:
            raise AssistantError("class_file", f"Question {index}: {exc.message}") from exc
        if question.id in seen:
            raise AssistantError("class_file", f"Question {index}: ID {question.id} is already used.")
        seen.add(question.id)
        questions.append(question)
    return questions


def _test_dir(root: Path, class_folder: str, test_folder: str) -> Path:
    if not isinstance(test_folder, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", test_folder):
        raise AssistantError("class_file", "That practice test name is not allowed.")
    folder = practice_dir(root, class_folder) / test_folder
    if folder.is_symlink() or not folder.is_dir():
        raise AssistantError("class_file", "That practice test does not exist.")
    return folder


def _parse_block(block: str) -> Question:
    fields = _fields(block)
    identifier = _require(fields, "ID")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", identifier):
        raise AssistantError("class_file", "ID must be letters, numbers, dots, or hyphens.")
    kind = _require(fields, "TYPE").upper()
    if kind not in {"MC", "TF", "SALL"}:
        raise AssistantError("class_file", "TYPE must be MC, TF, or SALL.")
    prompt = _require(fields, "PROMPT")
    raw_choices = fields.get("CHOICES", "")
    if kind == "TF" and not raw_choices.strip():
        choices = _TF_CHOICES
    else:
        if kind in {"MC", "SALL"} and not raw_choices.strip():
            raise AssistantError("class_file", "CHOICES is required for " + kind + ".")
        choices = _parse_choices(raw_choices)
        if not choices and kind != "TF":
            raise AssistantError("class_file", "CHOICES needs at least one option, such as A) Yes.")
    answers = _parse_answers(_require(fields, "ANSWER"), kind)
    if kind == "MC" and len(answers) != 1:
        raise AssistantError("class_file", "MC ANSWER must be one letter.")
    labels = {label for label, _text in choices}
    missing = answers - labels
    if missing:
        raise AssistantError("class_file", "ANSWER uses a letter that is not in CHOICES.")
    explanation = fields.get("EXPLANATION", "").strip()
    tags = tuple(
        part.strip()
        for part in re.split(r"[,;]", fields.get("TAGS", ""))
        if part.strip()
    )
    return Question(identifier, kind, prompt, choices, frozenset(answers), explanation, tags, block.strip())


def _fields(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key in _KEYS:
        prefix = key + ":"
        start = block.find(prefix)
        if start < 0:
            continue
        start += len(prefix)
        end = len(block)
        for match in _KEY_SPLIT.finditer(block):
            if match.start() >= start:
                end = match.start()
                break
        found[key] = block[start:end].strip()
    return found


def _require(fields: dict[str, str], key: str) -> str:
    value = fields.get(key, "").strip()
    if not value:
        raise AssistantError("class_file", f"Missing {key}.")
    return value


def _parse_choices(text: str) -> tuple[tuple[str, str], ...]:
    choices: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = _CHOICE_LINE.match(line.strip())
        if match:
            choices.append((match.group(1), match.group(2).strip()))
    return tuple(choices)


def _parse_answers(answer: str, kind: str) -> set[str]:
    if kind == "TF":
        folded = answer.strip().upper()
        if folded == "TRUE":
            return {"A"}
        if folded == "FALSE":
            return {"B"}
        raise AssistantError("class_file", "TF ANSWER must be TRUE or FALSE.")
    labels = {part.strip().upper() for part in answer.split(",") if part.strip()}
    if not labels:
        raise AssistantError("class_file", "ANSWER cannot be empty.")
    return labels
