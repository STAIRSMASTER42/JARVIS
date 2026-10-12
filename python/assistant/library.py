"""Local page for browsing classes, assignments, notes, and source files."""

from __future__ import annotations

import email
import html
import json
import mimetypes
import re
import threading
from email import policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from assistant.classes import (
    _assignment_dir,
    _course_dir,
    add_assignment,
    course_title,
    ensure_workspace,
    list_assignments,
    save_source,
    source_filename,
)
from assistant.errors import AssistantError
from assistant.practice import (
    grade_answer,
    list_practice_tests,
    load_questions,
    mark_for_review,
    public_questions,
    question_by_id,
)
from assistant.writing import add_writing, piece_count, writing_file

LIBRARY_PORT = 8766
_CLASS_PATH = re.compile(r"^/class/([^/]+)$")
_ASSIGNMENT_PATH = re.compile(r"^/class/([^/]+)/assignments/([^/]+)$")
_ASSIGNMENT_POST = re.compile(r"^/class/([^/]+)/assignments$")
_SOURCE_POST = re.compile(r"^/class/([^/]+)/assignments/([^/]+)/sources$")
_SOURCE_GET = re.compile(r"^/class/([^/]+)/assignments/([^/]+)/sources/([^/]+)$")
_PRACTICE_PATH = re.compile(r"^/class/([^/]+)/practice/([^/]+)(/review)?(/(questions|grade))?$")

_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #f5f5f7;
  --text: #1d1d1f;
  --muted: #6e6e73;
  --card: #ffffff;
  --line: rgba(0, 0, 0, 0.08);
  --accent: #0071e3;
  --danger: #b42318;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1c1e;
    --text: #f5f5f7;
    --muted: #aeaeb2;
    --card: #2c2c2e;
    --line: rgba(255, 255, 255, 0.12);
    --accent: #0a84ff;
    --danger: #ff6961;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
}
main { max-width: 720px; margin: 0 auto; padding: 28px 16px 48px; }
a { color: var(--accent); }
.brand { margin: 0 0 20px; }
.brand a { font-weight: 600; text-decoration: none; }
.brand span { color: var(--muted); }
h1 { font-size: 28px; margin: 0 0 6px; }
.muted, .sub { color: var(--muted); }
.sub { margin: 0 0 18px; }
a.card, .note, form, .error {
  background: var(--card);
  border-radius: 12px;
}
a.card {
  display: block;
  color: inherit;
  text-decoration: none;
  padding: 14px 16px;
  margin: 0 0 8px;
}
a.card strong { display: block; }
a.card span, .file span { color: var(--muted); font-size: 13px; }
.note { padding: 14px 16px; margin: 0 0 12px; }
.note h2, .note h3 { margin: 12px 0 6px; }
.note h2 { font-size: 18px; }
.note h3 { font-size: 16px; }
.note p { margin: 0 0 8px; }
h2.section { font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin: 22px 0 8px; }
form { padding: 12px; margin: 8px 0 18px; display: flex; gap: 8px; flex-wrap: wrap; }
input, button { font: inherit; }
input[type="text"], input[type="file"] {
  flex: 1;
  min-width: 160px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: inherit;
  border-radius: 8px;
  padding: 8px 10px;
}
button, .button {
  border: 0;
  background: var(--accent);
  color: white;
  border-radius: 8px;
  padding: 8px 12px;
  text-decoration: none;
}
textarea {
  width: 100%;
  min-height: 180px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: inherit;
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}
form.stack { flex-direction: column; align-items: stretch; }
.error { color: var(--danger); padding: 12px 14px; }
.file { margin: 0 0 8px; }
.prompt { font-size: 18px; margin: 0 0 12px; }
.choice { display: flex; gap: 8px; align-items: flex-start; margin: 0 0 8px; }
.quiz-actions { display: flex; gap: 8px; margin: 16px 0; }
.feedback { font-weight: 600; margin: 0; }
.feedback.ok { color: #1b7f3a; }
.feedback.bad { color: var(--danger); }
#explanation { margin: 8px 0 0; }
"""


def page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<p class="brand"><a href="/">Jarvis</a> <span>Classes</span></p>
{body}
</main>
<script>
document.addEventListener("copy", (event) => {{
  const selection = document.getSelection();
  if (!selection || selection.isCollapsed) return;
  event.preventDefault();
  event.clipboardData.setData("text/plain", selection.toString());
}});
</script>
</body>
</html>
"""


def _banner(error: str) -> str:
    if not error:
        return ""
    return f'<p class="error">{html.escape(error)}</p>'


def render_note(text: str) -> str:
    if not text.strip():
        return "<p class='muted'>No notes yet.</p>"
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith("# "):
            chunks.append(f"<h2>{html.escape(line[2:].strip())}</h2>")
        elif line.startswith("## "):
            chunks.append(f"<h3>{html.escape(line[3:].strip())}</h3>")
        elif line.strip():
            chunks.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(chunks) or "<p class='muted'>No notes yet.</p>"


def _read_text(path: Path) -> str:
    if path.is_file() and not path.is_symlink():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def classes_page(root: Path, error: str = "") -> str:
    courses = sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
    )
    if not courses:
        cards = (
            "<p class='sub'>No classes yet. Ask Jarvis to add one, or create it with "
            "<code>scripts/run.sh classes add --title \"Biology 101\"</code>.</p>"
        )
    else:
        items: list[str] = []
        for course in courses:
            count = len(list_assignments(root, course.name))
            label = "1 assignment" if count == 1 else f"{count} assignments"
            practice_count = len(list_practice_tests(root, course.name))
            if practice_count:
                label += " · " + ("1 practice test" if practice_count == 1 else f"{practice_count} practice tests")
            href = "/class/" + quote(course.name)
            items.append(
                f'<a class="card" href="{href}"><strong>{html.escape(course_title(course))}</strong>'
                f"<span>{label}</span></a>"
            )
        cards = "\n".join(items)
    body = (
        _banner(error)
        + "<h1>Classes</h1><p class='sub'>Choose a class to see its assignments.</p>"
        + cards
        + "<h2 class='section'>Not a class</h2>"
        + _writing_card(root)
    )
    return page("Classes", body)


def _writing_card(classes_root: Path) -> str:
    count = piece_count(writing_file(classes_root))
    label = "No writing yet" if count == 0 else ("1 piece" if count == 1 else f"{count} pieces")
    return (
        '<a class="card" href="/writing"><strong>My writing</strong>'
        f"<span>{label}. Your writing, for when you want Jarvis to write like you.</span></a>"
    )


def writing_page(classes_root: Path, error: str = "") -> str:
    path = writing_file(classes_root)
    text = ""
    if path.is_file() and not path.is_symlink():
        text = path.read_text(encoding="utf-8", errors="replace")
    if piece_count(path) == 0:
        shown = "<p class='muted'>No writing yet. Add a piece below.</p>"
    else:
        shown = f"<div class='note'>{render_note(text)}</div>"
    body = (
        f"{_banner(error)}<h1>My writing</h1>"
        "<p class='sub'><a href='/'>All classes</a></p>"
        "<p class='sub'>This is not a class. Add your own writing here. "
        "When you ask Jarvis to write like you, it reads this file. Jarvis cannot add to it.</p>"
        f"{shown}"
        "<form class='stack' method='post' action='/writing'>"
        "<input type='text' name='title' required placeholder='Title'>"
        "<textarea name='text' required placeholder='Paste your writing'></textarea>"
        "<button type='submit'>Add writing</button></form>"
    )
    return page("My writing", body)


def class_page(root: Path, class_folder: str, error: str = "") -> str:
    course = _course_dir(root, class_folder)
    title = course_title(course)
    assignments = list_assignments(root, class_folder)
    if assignments:
        cards = "\n".join(
            (
                f'<a class="card" href="/class/{quote(class_folder)}/assignments/{quote(item["slug"])}">'
                f'<strong>{html.escape(item["title"])}</strong>'
                f'<span>{html.escape(_due_label(item["due"]))}</span></a>'
            )
            for item in assignments
        )
    else:
        cards = "<p class='muted'>No assignments yet.</p>"
    notes = _read_text(course / "notes.md")
    action = f"/class/{quote(class_folder)}/assignments"
    body = (
        f"{_banner(error)}<h1>{html.escape(title)}</h1>"
        f"<p class='sub'><a href='/'>All classes</a></p>"
        f"<h2 class='section'>Assignments</h2>{cards}"
        f"<form method='post' action='{action}'>"
        f"<input type='text' name='title' required placeholder='Assignment title'>"
        f"<input type='text' name='due' placeholder='Due date'>"
        f"<button type='submit'>Add assignment</button></form>"
        f"<h2 class='section'>Practice tests</h2>{_practice_cards(root, class_folder)}"
        f"<h2 class='section'>Class notes</h2><div class='note'>{render_note(notes)}</div>"
    )
    return page(title, body)


def _practice_cards(root: Path, class_folder: str) -> str:
    tests = list_practice_tests(root, class_folder)
    if not tests:
        return "<p class='muted'>No practice tests yet. Ask Jarvis for one, such as Unit 1 or a midterm.</p>"
    items: list[str] = []
    for item in tests:
        count = int(item["count"])
        count_label = "1 question" if count == 1 else f"{count} questions"
        href = f"/class/{quote(class_folder)}/practice/{quote(str(item['slug']))}"
        items.append(
            f'<a class="card" href="{href}"><strong>{html.escape(str(item["title"]))}</strong>'
            f"<span>{count_label}</span></a>"
        )
        if int(item["review_count"]):
            items.append(f'<p class="file"><a href="{href}/review">Review marked questions</a></p>')
    return "\n".join(items)


def quiz_page(root: Path, class_folder: str, test_folder: str, *, review: bool = False) -> str:
    title, _questions = load_questions(root, class_folder, test_folder, review=review)
    back = f"/class/{quote(class_folder)}"
    base = f"{back}/practice/{quote(test_folder)}" + ("/review" if review else "")
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p class='sub'><a href='{back}'>Back to class</a></p>"
        "<p id='quiz-header' class='sub'></p><div id='quiz'></div>"
        "<script>\n"
        f"const questionsUrl = {json.dumps(base + '/questions')};\n"
        f"const gradeUrl = {json.dumps(base + '/grade')};\n"
        f"const showReview = {str(not review).lower()};\n"
        """const header = document.getElementById("quiz-header");
const quiz = document.getElementById("quiz");
let questions = [];
let index = 0;
let correctCount = 0;

function el(tag, text) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
}

function render() {
  quiz.replaceChildren();
  const question = questions[index];
  header.textContent = "Question " + (index + 1) + " / " + questions.length;
  const prompt = el("p", question.prompt);
  prompt.className = "prompt";
  quiz.appendChild(prompt);
  if (question.type === "SALL") quiz.appendChild(el("p", "Select all that apply."));
  question.choices.forEach((choice) => {
    const row = el("label");
    row.className = "choice";
    const input = document.createElement("input");
    input.type = question.type === "SALL" ? "checkbox" : "radio";
    input.name = "choice";
    input.value = choice.label;
    row.appendChild(input);
    row.appendChild(document.createTextNode(" " + choice.label + ") " + choice.text));
    quiz.appendChild(row);
  });
  if (showReview) {
    const reviewRow = el("label");
    reviewRow.className = "choice";
    const reviewInput = document.createElement("input");
    reviewInput.type = "checkbox";
    reviewInput.id = "mark-review";
    reviewRow.appendChild(reviewInput);
    reviewRow.appendChild(document.createTextNode(" Mark for review"));
    quiz.appendChild(reviewRow);
  }
  const actions = el("div");
  actions.className = "quiz-actions";
  const submit = el("button", "Submit");
  submit.type = "button";
  const next = el("button", index + 1 === questions.length ? "Finish" : "Next");
  next.type = "button";
  next.disabled = true;
  const feedback = el("p", "");
  feedback.id = "feedback";
  const explanation = el("p", "");
  explanation.id = "explanation";
  actions.append(submit, next);
  quiz.append(actions, feedback, explanation);
  submit.addEventListener("click", () => submitAnswer(question, submit, next, feedback, explanation));
  next.addEventListener("click", () => {
    index += 1;
    if (index >= questions.length) showScore();
    else render();
  });
}

async function submitAnswer(question, submit, next, feedback, explanation) {
  const selected = Array.from(quiz.querySelectorAll("input[name=choice]:checked")).map((node) => node.value);
  if (!selected.length) {
    feedback.textContent = "Choose an answer.";
    feedback.className = "feedback bad";
    return;
  }
  submit.disabled = true;
  const reviewBox = document.getElementById("mark-review");
  const response = await fetch(gradeUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: question.id,
      selected: selected,
      review: !!(reviewBox && reviewBox.checked)
    })
  });
  const result = await response.json();
  quiz.querySelectorAll("input").forEach((node) => { node.disabled = true; });
  if (!result.ok) {
    feedback.textContent = result.error || "That answer could not be checked.";
    feedback.className = "feedback bad";
    submit.disabled = false;
    quiz.querySelectorAll("input").forEach((node) => { node.disabled = false; });
    return;
  }
  if (result.correct) correctCount += 1;
  feedback.textContent = result.correct ? "Correct!" : "Incorrect.";
  feedback.className = result.correct ? "feedback ok" : "feedback bad";
  const parts = [];
  if (!result.correct && result.answer_text) parts.push("Answer: " + result.answer_text);
  if (result.explanation) parts.push(result.explanation);
  explanation.textContent = parts.join(" ");
  next.disabled = false;
}

function showScore() {
  header.textContent = "Finished";
  quiz.replaceChildren(el("p", "You got " + correctCount + " of " + questions.length + "."));
}

fetch(questionsUrl).then((response) => response.json()).then((payload) => {
  questions = payload.questions || [];
  if (!questions.length) {
    header.textContent = "This practice test has no questions.";
    return;
  }
  render();
}).catch(() => {
  header.textContent = "This practice test could not be opened.";
});
</script>"""
    )
    return page(title, body)


def assignment_page(root: Path, class_folder: str, assignment_folder: str, error: str = "") -> str:
    folder = _assignment_dir(root, class_folder, assignment_folder)
    title = _heading_file(folder / "assignment.md", assignment_folder)
    due = _due_label(_due_from_file(folder / "assignment.md"))
    notes = _note_blocks(folder)
    sources = _source_links(class_folder, assignment_folder, folder / "sources")
    back = f"/class/{quote(class_folder)}"
    upload = f"{back}/assignments/{quote(assignment_folder)}/sources"
    body = (
        f"{_banner(error)}<h1>{html.escape(title)}</h1>"
        f"<p class='sub'>{html.escape(due)} · <a href='{back}'>Back to class</a></p>"
        f"<h2 class='section'>Notes</h2>{notes}"
        f"<h2 class='section'>Sources</h2>{sources}"
        f"<form method='post' action='{upload}' enctype='multipart/form-data'>"
        f"<input type='file' name='source' required>"
        f"<button type='submit'>Add file</button></form>"
    )
    return page(title, body)


def _due_label(due: str) -> str:
    if not due or due.lower() == "unknown":
        return "No due date"
    return f"Due {due}"


def _due_from_file(path: Path) -> str:
    for line in _read_text(path).splitlines():
        if line.lower().startswith("- due:"):
            return line.split(":", 1)[1].strip()
    return ""


def _heading_file(path: Path, fallback: str) -> str:
    for line in _read_text(path).splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            if title:
                return title
    return fallback


def _note_blocks(folder: Path) -> str:
    files = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() == ".md" and path.name != "assignment.md"
    )
    if not files:
        return "<p class='muted'>No notes yet.</p>"
    blocks: list[str] = []
    for path in files:
        blocks.append(
            f"<p class='file'><span>{html.escape(path.name)}</span></p>"
            f"<div class='note'>{render_note(_read_text(path))}</div>"
        )
    return "\n".join(blocks)


def _source_links(class_folder: str, assignment_folder: str, sources: Path) -> str:
    if not sources.is_dir() or sources.is_symlink():
        return "<p class='muted'>No sources yet.</p>"
    files = sorted(
        path
        for path in sources.iterdir()
        if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
    )
    if not files:
        return "<p class='muted'>No sources yet. Add a file.</p>"
    items: list[str] = []
    for path in files:
        href = (
            f"/class/{quote(class_folder)}/assignments/{quote(assignment_folder)}/sources/{quote(path.name)}"
        )
        items.append(f'<p class="file"><a href="{href}">{html.escape(path.name)}</a></p>')
    return "\n".join(items)


def source_file(root: Path, class_folder: str, assignment_folder: str, filename: str) -> Path:
    folder = _assignment_dir(root, class_folder, assignment_folder) / "sources" / source_filename(filename)
    if folder.is_symlink() or not folder.is_file():
        raise AssistantError("class_file", "That source file does not exist.")
    resolved = folder.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise AssistantError("class_file", "That path is outside the classes folder.")
    return folder


class LibraryHandler(BaseHTTPRequestHandler):
    server: LibraryServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        error = parse_qs(parsed.query).get("error", [""])[0]
        path = unquote(parsed.path)
        root = self.server.library_root
        try:
            if path == "/health":
                self._send(200, "text/plain; charset=utf-8", b"jarvis-classes")
                return
            if path == "/":
                self._send_html(classes_page(root, error))
                return
            if path == "/writing":
                self._send_html(writing_page(root, error))
                return
            practice_match = _PRACTICE_PATH.match(path)
            if practice_match:
                self._practice_get(root, practice_match)
                return
            class_match = _CLASS_PATH.match(path)
            if class_match:
                self._send_html(class_page(root, class_match.group(1), error))
                return
            assignment_match = _ASSIGNMENT_PATH.match(path)
            if assignment_match:
                self._send_html(assignment_page(root, assignment_match.group(1), assignment_match.group(2), error))
                return
            source_match = _SOURCE_GET.match(path)
            if source_match:
                self._send_file(source_file(root, source_match.group(1), source_match.group(2), source_match.group(3)))
                return
        except AssistantError:
            self._send_html(page("Not found", "<p>That page is not in the classes folder.</p><p><a href='/'>Back to classes</a></p>"), 404)
            return
        self._send_html(page("Not found", "<p>That page is not in the classes folder.</p><p><a href='/'>Back to classes</a></p>"), 404)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        root = self.server.library_root
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > (25 * 1024 * 1024) + 200_000:
            self._send_html(page("Too large", "<p>That file is larger than 25 MB.</p>"), 413)
            return
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        assignment_post = _ASSIGNMENT_POST.match(path)
        if assignment_post:
            self._create_assignment(root, assignment_post.group(1), body)
            return
        source_post = _SOURCE_POST.match(path)
        if source_post:
            self._upload_source(root, source_post.group(1), source_post.group(2), content_type, body)
            return
        if path == "/writing":
            self._add_writing(root, body)
            return
        practice_match = _PRACTICE_PATH.match(path)
        if practice_match and practice_match.group(5) == "grade":
            self._grade_practice(root, practice_match, body)
            return
        self._send_html(page("Not found", "<p>That page is not in the classes folder.</p>"), 404)

    def _create_assignment(self, root: Path, class_folder: str, body: bytes) -> None:
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        title = fields.get("title", [""])[0]
        due = fields.get("due", [""])[0]
        back = "/class/" + quote(class_folder)
        try:
            folder = add_assignment(root, class_folder, title, due)
        except AssistantError as exc:
            self._redirect(back + "?error=" + quote(exc.message))
            return
        self._redirect(f"{back}/assignments/{quote(folder.name)}")

    def _upload_source(self, root: Path, class_folder: str, assignment_folder: str, content_type: str, body: bytes) -> None:
        back = f"/class/{quote(class_folder)}/assignments/{quote(assignment_folder)}"
        try:
            filename, data = _uploaded_file(content_type, body)
            save_source(root, class_folder, assignment_folder, filename, data)
        except AssistantError as exc:
            self._redirect(back + "?error=" + quote(exc.message))
            return
        self._redirect(back)

    def _practice_get(self, root: Path, match: re.Match[str]) -> None:
        class_folder, test_folder = match.group(1), match.group(2)
        review = match.group(3) == "/review"
        action = match.group(5)
        try:
            if action == "grade":
                self._send_json({"ok": False, "error": "Submit an answer to check it."}, 405)
                return
            if action == "questions":
                _title, questions = load_questions(root, class_folder, test_folder, review=review)
                self._send_json({"questions": public_questions(questions)})
                return
            self._send_html(quiz_page(root, class_folder, test_folder, review=review))
        except AssistantError as exc:
            if action == "questions":
                self._send_json({"ok": False, "error": exc.message}, 404)
                return
            back = "/class/" + quote(class_folder)
            self._send_html(
                page("Practice test", f"<p class='error'>{html.escape(exc.message)}</p><p><a href='{back}'>Back to class</a></p>"),
                404,
            )

    def _grade_practice(self, root: Path, match: re.Match[str], body: bytes) -> None:
        class_folder, test_folder = match.group(1), match.group(2)
        review = match.group(3) == "/review"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "That answer could not be checked."}, 400)
            return
        if not isinstance(payload, dict):
            self._send_json({"ok": False, "error": "That answer could not be checked."}, 400)
            return
        selected = payload.get("selected") or []
        if not isinstance(selected, list) or not selected:
            self._send_json({"ok": False, "error": "Choose an answer."}, 400)
            return
        try:
            _title, questions = load_questions(root, class_folder, test_folder, review=review)
            question = question_by_id(questions, str(payload.get("id", "")))
            if payload.get("review") and not review:
                mark_for_review(root, class_folder, test_folder, question)
        except AssistantError as exc:
            self._send_json({"ok": False, "error": exc.message}, 404)
            return
        correct = grade_answer(question, [str(item) for item in selected])
        lookup = dict(question.choices)
        answer_text = ", ".join(f"{letter}) {lookup.get(letter, letter)}" for letter in sorted(question.answers))
        self._send_json(
            {
                "ok": True,
                "correct": correct,
                "explanation": question.explanation,
                "answer_text": answer_text,
            }
        )

    def _add_writing(self, root: Path, body: bytes) -> None:
        fields = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        title = fields.get("title", [""])[0]
        text = fields.get("text", [""])[0]
        try:
            add_writing(root, title, text)
        except AssistantError as exc:
            self._redirect("/writing?error=" + quote(exc.message))
            return
        self._redirect("/writing")

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, markup: str, status: int = 200) -> None:
        self._send(status, "text/html; charset=utf-8", markup.encode("utf-8"))

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        guessed, _ = mimetypes.guess_type(path.name)
        content_type = guessed or "application/octet-stream"
        inline = path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".md"}
        disposition = "inline" if inline else "attachment"
        filename = path.name.replace('"', "")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f'{disposition}; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        self._send(status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))

    def _send(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


class LibraryServer(ThreadingHTTPServer):
    library_root: Path
    allow_reuse_address = True

    def __init__(self, root: Path, port: int) -> None:
        self.library_root = ensure_workspace(root)
        super().__init__(("127.0.0.1", port), LibraryHandler)


def serve_library(root: Path, port: int = LIBRARY_PORT) -> None:
    server = LibraryServer(root, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


def start_library(root: Path, port: int = 0) -> LibraryServer:
    """Start the classes page on a background thread. Port 0 chooses a free port."""
    server = LibraryServer(root, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _uploaded_file(content_type: str, body: bytes) -> tuple[str, bytes]:
    if "multipart/form-data" not in content_type.lower():
        raise AssistantError("class_file", "Choose a file to add.")
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = email.message_from_bytes(header + body, policy=policy.default)
    if not message.is_multipart():
        raise AssistantError("class_file", "Choose a file to add.")
    for part in message.iter_parts():
        filename = part.get_filename()
        if not filename:
            continue
        data = part.get_payload(decode=True) or b""
        return filename, data
    raise AssistantError("class_file", "Choose a file to add.")
