# Jarvis

A menu-bar school assistant for macOS. Press **Control + Option + ]** to open a small floating window at the upper-right of the display under the pointer. The window is Jarvis. It does not capture the screen when it opens. **Add screenshot** captures that display and sends the image to the OpenAI Responses API. You can also type a question with no screenshot.

Jarvis does not watch the screen in the background. A capture happens only when you press **Add screenshot**. The popup hides itself for a moment before the capture so the window is not in the picture.

Version 1.0.0.

## What it does

- Answers quiz and assignment questions from a screenshot, using the class notes and source files on this Mac.
- Takes notes from a textbook screenshot and saves them in the matching class or assignment.
- Keeps a local classes folder: courses, assignments, due dates, notes, class files, and assignment sources.
- Shows those files in a browser page that only this Mac can open.
- Builds a to-do list from assignment due dates and lets you mark work done.
- Writes practice tests from a class’s notes and sources. You take them in the browser.
- Matches your voice when **Write like me** is on, using a file only you can add to.
- Puts an essay in a plain text box under a short comment, with its own **Copy essay** button.

Follow-up questions stay in that popup and reuse the same OpenAI response, so an earlier screenshot is not uploaded again. Closing the panel ends the session and drops that response id.

## How it is put together

Hammerspoon listens for the shortcut, draws the popup, and captures the display. A Python virtualenv in this project talks to OpenAI and reads and writes the class files. Your API key stays in the macOS Keychain (or in `OPENAI_API_KEY`) and is never written into this repository.

```
Control-Option-]
  → floating panel on the display under the pointer
Add screenshot
  → panel hides
  → Hammerspoon captures that display to a temporary PNG
  → panel shows a spinner
  → scripts/run.sh analyze
  → sips resizes the PNG to a JPEG and deletes both files
  → OpenAI Responses API
  → answer in the popup
```

A typed message with no screenshot uses `scripts/run.sh followup`. If a conversation is already open, both commands send `previous_response_id` so OpenAI keeps the earlier turn.

When class files are enabled, the model can call tools (read a note, create an assignment, edit a due date, and so on). Python runs the tool on this Mac and sends the result back. That loop stops at 50 tool rounds. If classes are on, the request asks for at least 8,000 output tokens so a long note or practice test can finish, even when `max_output_tokens` in the config is lower.

The classes page is a small web server on `127.0.0.1:8766`. It starts the first time you press **Classes**. It is not reachable from another computer.

```
Popup or menu
  → scripts/run.sh classes serve
  → http://127.0.0.1:8766/
  → browser
```

## Requirements

- macOS 13 or newer
- [Homebrew](https://brew.sh)
- Python 3.10 or newer. The installer uses Homebrew’s Python 3.12 when it cannot find 3.10 or newer.
- [Hammerspoon](https://www.hammerspoon.org). The installer adds it with `brew install --cask hammerspoon` if `/Applications/Hammerspoon.app` is missing.
- An OpenAI API key with access to a vision model

Python packages, from `requirements.txt`:

- `openai` 1.68 or newer
- `pypdf` 5 or newer, used to read PDF source files

Word documents are read with macOS `textutil`. Screenshots are resized with macOS `sips`. Neither is a Python package.

## Install

```bash
git clone <this-repo> ~/Projects/mac-ai-assistant
cd ~/Projects/mac-ai-assistant
scripts/install.sh
```

The installer:

- Refuses to run on anything other than macOS
- Installs Hammerspoon if it is missing, which needs Homebrew
- Looks for Python 3.13, 3.12, or 3.11 under Homebrew, then installs `python@3.12` if none of those is new enough
- Creates `.venv` and installs `requirements.txt`
- Copies `config.example.json` to `~/.config/mac-ai-assistant/config.json` if you do not already have one
- Writes `~/.config/mac-ai-assistant/install.json` with the absolute path of this project, so Hammerspoon can find `scripts/run.sh` after the symlink is in place
- Asks for an API key and stores it in Keychain
- Symlinks `~/.hammerspoon/mac-ai-assistant` to this project’s `hammerspoon/` directory
- Appends a marked block to `~/.hammerspoon/init.lua` without removing other Hammerspoon config. The marker is `mac-ai-assistant (managed)`. Running the installer again does not add a second copy.
- Adds Hammerspoon as a login item
- Opens Hammerspoon and reloads its config

Run `scripts/install.sh --yes` to skip the key prompt. That is useful when `OPENAI_API_KEY` is already set, or when you will run `scripts/setup-key.sh` afterward. If the variable is set, the installer stores it even with `--yes`.

## API key

Each Mac has its own key. Store or replace it with:

```bash
scripts/setup-key.sh
```

The script reads `OPENAI_API_KEY` when that variable is set. Otherwise it prompts in the terminal and does not echo the key. It writes a login-Keychain item:

| Field | Value |
|---|---|
| Service | `mac-ai-assistant-openai` |
| Account | `charliebaker` |

The assistant reads it with `/usr/bin/security find-generic-password`. The key is not placed on the command line of that lookup. `setup-key.sh` also trusts the project’s `.venv` Python and `/usr/bin/security` for that item (`security -T`), so later reads are less likely to prompt.

You can instead export `OPENAI_API_KEY` in the environment Hammerspoon can see. The environment variable is checked first. Do not put the key in `config.json` or in git.

The first request may still show a Keychain prompt for `python`. Choose **Always Allow**.

Messages shown in the popup are scrubbed for strings that look like `sk-…` keys or `Bearer` tokens.

## Permissions

macOS will not grant these until you approve them:

| Permission | Why | Where |
|---|---|---|
| Accessibility | The shortcut must work while another app is focused | System Settings → Privacy & Security → Accessibility → Hammerspoon |
| Screen Recording | Capture the display | System Settings → Privacy & Security → Screen Recording → Hammerspoon |
| Keychain | Read the API key | Prompt on the first request |

After changing Screen Recording, quit Hammerspoon and open it again. A denied or empty capture shows the same instructions in the popup. If Accessibility is off when the assistant starts, Hammerspoon posts a notification.

The panel is a non-activating floating utility window (`titled`, `closable`, `utility`, `nonactivating`). It is set to join all Spaces, stay put when you switch apps, and stay out of the window cycle. It can appear over Safari, Chrome, Preview, or the desktop without becoming the front application. Dark mode follows the system appearance. Confirm focus behavior on your Mac after install; it depends on Hammerspoon.

Links in a reply open in your browser. The popup does not navigate itself.

## Use it

1. Run `scripts/launch.sh` (or open Hammerspoon and choose **Reload Config**).
2. An **AI** item appears in the menu bar. Its tooltip is “Screen Assistant”.
3. Press **Control + Option + ]**, or choose **AI → Open Jarvis**.

The window opens without taking a screenshot. Drag the title bar to move it. **Close** or **Escape** dismisses it and cancels any request that is still running.

### Talking to Jarvis

Type in the box and press Return (or **Send**) to send a message. A screenshot is optional. The first message in a session starts a new OpenAI response. Later messages in the same open panel continue it.

**Add screenshot** captures the display under the pointer and keeps this conversation, so a later page or question stays in the same context. Text in the box is sent with that screenshot. The panel hides for about 0.15 seconds first so it is not in the image. The capture is a PNG in the temporary directory, named `mac-ai-assistant-<time>-<random>.png`.

While a request is running the input, **Send**, **Write like me**, and **Add screenshot** are disabled, and the status line shows a spinner (“Asking OpenAI…”). Pressing the shortcut again only brings the panel forward. Pressing **Send** or **Add screenshot** while busy flashes “A request is already running.” A request that is still going after 180 seconds is killed, and the popup says it took too long. The OpenAI client timeout is separate and comes from `timeout_seconds` (45 seconds by default).

**Copy** puts the conversation bubbles on the clipboard and flashes “Copied.” It does not include the essay box. **Copy essay**, on an essay, copies only that essay.

### Write like me

**Write like me** is a switch. Turn it on, then **Send** or **Add screenshot**. The click turns the button into **Write like me on**.

Jarvis will not imitate you unless that switch is on or you ask it to write like you. With the switch on, the whole My writing file is placed in the prompt, and the instruction tells the model to:

- Use only words found in that file, except a couple of extra words when one is needed
- Use the phrase “Including but not limited to” as much as possible
- Include one comparison to lawn keeping in each writing assignment, and choose a different comparison each time
- Put the writing itself between `---essay---` and `---end---`

If My writing is empty, the request fails with “Add writing in My writing before using Write like me.”

### Essays

When the reply contains a block between a line that is exactly `---essay---` and a line that is exactly `---end---`, the popup splits it:

- Text outside the markers stays in the chat as the comment.
- The text between the markers is shown in a plain text box. Markdown, bold, and headings are stripped.
- **Copy essay** copies only that box.

The default instruction tells Jarvis to do this for an essay or other piece of writing, and to keep the writing plain: no bold, no markdown, no asterisks, and no headings.

### Menu bar

The **AI** menu:

| Item | What it does |
|---|---|
| **Open Jarvis** | Opens the panel even when the hotkey is disabled. The label includes the current shortcut, such as ⌃⌥]. |
| **Disable shortcut** / **Enable shortcut** | Leaves the assistant loaded but ignores the hotkey. **Open Jarvis** still works. |
| **Reload config** | Rereads `config.json` and rebinds the hotkey. |
| **Quit Screen Assistant** | Unloads the hotkey, menu item, and popup. Other Hammerspoon config keeps running. |

From a terminal:

- `scripts/quit.sh` unloads the assistant. Hammerspoon itself stays running.
- `scripts/launch.sh` opens Hammerspoon and reloads its config.
- To stop Hammerspoon opening at login, disable **Launch Hammerspoon at login** in Hammerspoon’s preferences, or remove the Hammerspoon login item.

`quit.sh` needs the `hs` command-line tool (inside the Hammerspoon app, or on the Homebrew path). If it cannot find `hs`, use the menu item instead.

## Configuration

Edit `~/.config/mac-ai-assistant/config.json`, then choose **Reload config** from the AI menu or run `scripts/launch.sh`.

A missing config file uses the built-in defaults. A partial file is merged on top of those defaults, including nested objects such as `shortcut` and `popup`. Invalid JSON, a non-object file, or a value outside the ranges below fails the request with a config error. Hammerspoon itself only reads `shortcut` and `popup` from the file. If the file is invalid JSON, Hammerspoon keeps the default shortcut and posts a notification. The Python side still validates the full file when a request runs.

| Field | Default | Allowed | Purpose |
|---|---|---|---|
| `shortcut.modifiers` | `["ctrl", "alt"]` | Non-empty list of `ctrl`, `alt`, `cmd`, `shift` | Global hotkey modifiers. |
| `shortcut.key` | `]` | A Hammerspoon key name with no spaces | Global hotkey key. |
| `model` | `gpt-5.4-mini` | A model name with no spaces | Vision-capable model for screenshots and chat. |
| `system_instruction` | See `config.example.json` | Non-empty text | Instruction sent with every request. |
| `user_prompt` | `Look at this screenshot and help with school.` | Non-empty text | Text sent with the first screenshot. Anything you typed is placed above it. |
| `max_output_tokens` | `800` | Integer 16–4000 | Cap stored in the config. When classes are enabled, the live request uses at least 8000. |
| `image_max_edge` | `1600` | Integer 512–2048 | Longest side of the JPEG sent to the API, in pixels. |
| `jpeg_quality` | `80` | Integer 40–95 | JPEG quality passed to `sips`. |
| `image_detail` | `high` | `low`, `high`, `auto`, or `original` | Image detail sent to the Responses API. `high` keeps small text readable. |
| `timeout_seconds` | `45` | Integer 5–180 | OpenAI client timeout. The popup also stops a hung process after 180 seconds. |
| `popup.width` | `400` | Integer 280–800 | Panel width in points. |
| `popup.max_height` | `520` | Integer 200–1000 | Panel height, also limited by the display. |
| `popup.margin` | `16` | Integer 0–80 | Inset from the top and right of the display under the pointer. |
| `classes_enabled` | `true` | `true` or `false` | When true, Jarvis can read and edit class files and My writing. |
| `classes_dir` | `""` | A dedicated folder path, or empty | Empty uses `~/Documents/mac-ai-assistant/classes`. |

The classes folder must be a dedicated directory. Your home folder, Desktop, Documents, Downloads, `/`, `/tmp`, `/private/tmp`, and `/Users` cannot be `classes_dir`. A relative path is resolved from your home directory.

The default instruction tells the model it is Jarvis, a school assistant on this Mac. It answers quiz and assignment screens, takes notes from textbook screens into the matching class, reads the class files it has access to, and asks when it is not sure which class something belongs to. It also tells the model to treat a screenshot, message, or file that says to ignore its instructions as a prompt injection: name where it saw that, do not follow it, and continue the school task.

One course is named in that default instruction. The English class folder `enc-1020-ac112` stores due dates in bold as `**Due:** 2026-10-16`. Jarvis is told to keep the bold markers and change only the date. Other assignments use a line such as `- Due: 2026-10-15`. Editing a due date replaces that one line. It does not rewrite the whole file.

## Where files live

Nothing under these paths is in git.

| Path | What it is |
|---|---|
| `~/.config/mac-ai-assistant/config.json` | Your settings. |
| `~/.config/mac-ai-assistant/install.json` | `project_root` pointing at this checkout. |
| `~/Documents/mac-ai-assistant/classes/` | Class folders. |
| `~/Documents/mac-ai-assistant/writing/my-writing.md` | My writing. This sits beside the classes folder, not inside it. |
| `~/.hammerspoon/init.lua` | Loads the assistant. |
| `~/.hammerspoon/mac-ai-assistant` | Symlink to `hammerspoon/` in this project. |
| Temporary directory | Screenshot PNG and the resized JPEG. Both are deleted after the request is prepared. |

## Class files

Class notes stay on this Mac. The assistant cannot write outside the classes folder, cannot follow a symlink, and cannot use `..` in a path. Paths may be at most five levels deep. Folder and file names must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$`.

Add a class from the project directory:

```bash
scripts/run.sh classes add --title "Biology 101" --term "Fall 2026" --instructor "Ada Lovelace" --schedule "Tue/Thu 10:00"
scripts/run.sh classes list
scripts/run.sh classes path
```

`--term`, `--instructor`, and `--schedule` are optional. The folder name is a slug of the title: ASCII, lowercase, hyphens, at most 60 characters. `Biology 101` becomes `biology-101`. Creating a slug that already exists is an error. You can also ask in the popup, for example “Add my Biology 101 class.”

Each class looks like this:

```text
biology-101/
  course.md            name, term, instructor, schedule, and what the class is about
  notes.md             class-wide notes
  assignments.md       a short class-level assignments page created with the class
  files/               files for the whole class, such as a syllabus or slides
  assignments/
    lab-report/
      assignment.md    title, due date, status, and what the assignment asks
      notes.md         notes for this assignment
      sources/         files you attach to this assignment only
  practice-tests/
    unit-1/
      title.txt
      questions.txt
      review.txt       created when you mark questions for review
```

`assignments.md` at the class root is created with the class. The assignments Jarvis and the classes page actually use are the folders under `assignments/`.

On a quiz or assignment, Jarvis answers the question and uses the matching class files, assignment notes, and source documents. For a multiple-choice question the default instruction asks for the letter, the text of the choice, and a short explanation. On a textbook screenshot, class-wide notes go in `notes.md` and notes about one assignment go in that assignment’s `notes.md`. If it cannot tell which class or assignment the screen belongs to, it asks. It is told not to invent course details, due dates, or notes that are not in the files or on the screen. After it changes a file, the reply names the path. Python also appends a line such as `Updated biology-101/notes.md.` listing every file or folder touched in that turn, unless the reply already contains that sentence.

Ask Jarvis to delete a class or an assignment when you want that folder removed. It deletes the folder and the files inside it, and it cannot delete anything outside the classes folder. It is told not to delete a folder unless you asked.

Set `classes_enabled` to `false` to turn class tools and My writing off. File contents are sent to OpenAI only as part of a request you start.

### What Jarvis can call

These tools are offered only when `classes_enabled` is true. Tool results are cut at 12,000 characters, except `read_my_writing`, which can return up to 4,000,000 characters. A tool error is returned to the model as text. It does not crash the popup.

| Tool | What it does |
|---|---|
| `list_class_files` | Catalog of classes, files, assignments, sources, and practice tests. |
| `read_class_file` | Read one note or source. |
| `search_class_files` | Case-insensitive search. Needs at least two characters. Stops at 30 matches and does not walk more than 200 files. |
| `create_assignment` | Creates `assignment.md`, `notes.md`, and `sources/` under that class. |
| `write_class_file` | Create or replace a text note (`.md`, `.txt`, `.json`, `.csv`). Not for PDFs or other attachments. |
| `edit_class_file` | Replace one exact passage. The old text must match once. |
| `mark_assignment_done` | Write or remove `- Status: done` in `assignment.md`. |
| `delete_folder` | Delete one class folder or one assignment folder. |
| `create_practice_test` | Create or replace one named practice test. |
| `read_my_writing` | Read My writing. The model cannot add to that file. |

Jarvis cannot create the files in `files/` or in an assignment’s `sources/`. You add those from the classes page. A single written note is capped at 120,000 characters. Text that looks like an API key is redacted before it is written.

### Reading sources

| Kind | How it is read |
|---|---|
| `.md`, `.txt`, `.json`, `.csv` | Read as UTF-8 text. |
| `.pdf` | Text extracted with `pypdf`, first 40 pages, with a `--- page N ---` marker. |
| `.doc`, `.docx` | Converted with `/usr/bin/textutil`. |
| Anything else | If the first 8 KB contains a null byte, Jarvis is told the file name and size and that the contents were not extracted. Otherwise the file is read as text. |

Extracted text is capped at 120,000 characters. A PDF or Word file that cannot be parsed returns a short sentence saying so, instead of failing the request.

### Assignments and the to-do list

An assignment folder is created with:

```markdown
# Lab report

- Due: 2026-10-15

## What this assignment asks
```

If no due date was given, the line is `- Due: unknown`.

Marking it done inserts `- Status: done` on the line after the due line, without rewriting the rest of the file. A status of `done`, `yes`, `complete`, or `completed` counts as finished, including when the line is bold. Marking it not done removes that line. Done assignments leave the active to-do list.

Due dates the to-do list understands:

- `2026-10-15`
- `10/15/2026` and `10/15/26`
- `10-15-2026`
- `October 15, 2026`, `Oct 15, 2026`, and the same forms without a comma
- `October 15` and `Oct 15` (year inferred; a date more than about 180 days in the past rolls to next year)

`unknown`, `none`, `n/a`, and `tbd` stay undated. Weekday names are not dates. The to-do list includes overdue work inside a day filter. Assignments with no calendar date appear only on **All**.

You can add an assignment from the class page as well as by asking Jarvis. The form takes a title and an optional due date.

### Practice tests

Open a class to see its practice tests. Ask Jarvis for one and name it, for example Unit 1 or Midterm. A class can have several. The same title again replaces that test. Jarvis is told to use only facts from that class’s notes, sources, or the screen.

Questions are stored in `questions.txt`, one block per question, with a blank line between blocks:

```text
ID: q1
TYPE: MC
PROMPT: What does the mitochondria produce?
CHOICES:
A) Protein
B) ATP
C) DNA
ANSWER: B
EXPLANATION: The notes describe ATP as the product.
TAGS: unit-1

ID: q2
TYPE: TF
PROMPT: The cell wall is outside the cell membrane.
ANSWER: TRUE

ID: q3
TYPE: SALL
PROMPT: Which of these are nucleotides?
CHOICES:
A) Adenine
B) Glucose
C) Cytosine
ANSWER: A, C
```

| Field | Rule |
|---|---|
| `ID` | Letters, numbers, dots, or hyphens. Unique inside the test. |
| `TYPE` | `MC` (one answer), `TF` (true/false), or `SALL` (select all). |
| `PROMPT` | The question. |
| `CHOICES` | Lines like `A) ATP`. Required for `MC` and `SALL`. Optional for `TF`, which defaults to TRUE and FALSE. |
| `ANSWER` | One letter for `MC`. `TRUE` or `FALSE` for `TF`. Comma-separated letters for `SALL`, such as `A, C`. |
| `EXPLANATION` | Optional. Shown after you submit. |
| `TAGS` | Optional. Comma or semicolon separated. |

Taking a test happens in the browser. The page loads the prompts and choices only. Answers stay on the server until you press **Submit**. A correct answer shows “Correct!” An incorrect one shows “Incorrect.”, the right answer, and the explanation. **Mark for review** on a question copies that question into `review.txt`. The class page then links to **Review marked questions**. At the end the page shows how many you got right.

A practice test file is capped at 120,000 characters.

## Classes window

**Classes** in the popup opens `http://127.0.0.1:8766/` in your browser. The server binds to loopback only. If it is already running, the button just opens the page. Health is `GET /health`, which returns `jarvis-classes`.

The page follows light and dark mode. Copying a selection puts plain text on the clipboard.

| Page | What you can do |
|---|---|
| **Classes** (`/`) | Every class, with open and done counts and how many practice tests it has. |
| **To-do** (`/todo`) | Assignments from every class. Filter to all, or to what is due in 1, 7, 30, or 90 days, including overdue. **Done** marks one finished. **Undo** puts it back. The home card counts how many are due within 7 days. |
| **Class** (`/class/<slug>`) | Notes, assignments, an add-assignment form, practice tests, and class files. |
| **Notes** | Class `notes.md` plus each assignment’s notes. |
| **Assignment** | Due date, done state, notes, and sources. |
| **My writing** (`/writing`) | Not a class. Add a title and paste your own writing. |
| **Practice test** | One question at a time, then a score. |

**Class files** are for anything that is not tied to one assignment, such as a syllabus. **Add file** on an assignment attaches a source for that assignment only. Uploads are limited to 25 MB. The original file name is cleaned up (spaces become hyphens, odd characters are dropped, hidden names are rejected). A second file with the same name is saved as `name-2.ext`, up to `name-99`. PDF, text, and common image types are shown in the browser. Other types download.

My writing pieces are appended to `my-writing.md` as `## Title` sections. Jarvis cannot add to that file. The file cannot grow past 4,000,000 characters, and a single pasted piece cannot exceed that either. Text that looks like an API key is redacted when you add a piece.

You can also start the page from a terminal. It runs until you interrupt it:

```bash
scripts/run.sh classes serve
```

## Command line

`scripts/run.sh` runs the project virtualenv with `python/assistant` on `PYTHONPATH`. If `.venv` is missing it prints a JSON error telling you to run `scripts/install.sh`.

```bash
scripts/run.sh analyze --image /tmp/screen.png --config ~/.config/mac-ai-assistant/config.json
scripts/run.sh analyze --image /tmp/page2.png --previous-id resp_... --text "This is the next page"
scripts/run.sh followup --text "What was the answer to question 2?" --previous-id resp_...
scripts/run.sh followup --text "Draft the intro" --like-me
scripts/run.sh test-connection --model gpt-5.4-nano
scripts/run.sh classes path
scripts/run.sh classes list
scripts/run.sh classes add --title "Biology 101" --term "Fall 2026"
scripts/run.sh classes serve
```

`analyze` and `followup` accept `--like-me` and `--config`. `analyze` also accepts `--keep-image`, which leaves the screenshot on disk for debugging. Without it, the PNG and the JPEG are deleted even when resizing fails.

Successful chat commands print one JSON object:

```json
{"ok": true, "text": "...", "response_id": "resp_..."}
```

Failures print `{"ok": false, "code": "...", "error": "..."}` and exit 1. The `classes` commands print plain text on success and write the error to stderr.

| Code | When you see it |
|---|---|
| `missing_api_key` | No `OPENAI_API_KEY` and no Keychain item. |
| `invalid_api_key` | OpenAI rejected the key (HTTP 401 or 403). |
| `quota` | Billing, quota, or rate limit (HTTP 402 or 429). |
| `network` | Could not reach OpenAI. |
| `timeout` | The client timed out. Raise `timeout_seconds` if this keeps happening. |
| `screenshot_permission` | The capture file was empty. Turn on Screen Recording and reopen Hammerspoon. |
| `image_error` | The file was missing, `sips` failed, resizing hung, or the JPEG was still over 8 MB. |
| `config_error` | The config file is invalid, or `classes_dir` is not a dedicated folder. |
| `bad_request` | Empty message, empty My writing with **Write like me**, or OpenAI rejected the request body. The model name is the first thing to check. |
| `bad_response` | The model returned no text, or it used tools 50 times without finishing. |
| `class_file` | A class, assignment, or practice-test change was rejected. |
| `not_installed` | `.venv` or the `openai` package is missing. |
| `unexpected` | Anything else. The message is shortened and scrubbed. |

The first screenshot’s prompt is your typed text, then `user_prompt`. A later screenshot uses your typed text plus a fixed line that this is another screenshot of the same schoolwork. A message with no screenshot sends only what you typed. An empty message is rejected before any API call.

## Check the API

This reads the key from Keychain (or the environment) and sends a short text request with no screenshot. It uses a small amount of API credit. The default model is `gpt-5.4-nano`, not the vision model in your config. Override it with `CONNECTION_MODEL` if you need to.

```bash
scripts/test-connection.sh
```

A working key looks like `{"ok": true, "text": "ok", ...}`. Failures use the same messages as the popup.

## Tests

Unit tests cover config parsing, error mapping, Keychain lookup (the `security` tool is mocked), request payloads, screenshot cleanup, class files, the to-do list, practice tests, My writing, the classes pages, and the CLI. They do not call OpenAI and do not open a window. One image test runs `sips` on a generated file and checks that the temporary files are deleted.

```bash
scripts/test.sh
```

`scripts/test.sh` uses `.venv` when it exists, and otherwise `python3` on your `PATH`.

## Project layout

```text
config.example.json          default config copied on install
requirements.txt             openai and pypdf
scripts/install.sh           Homebrew, venv, Keychain, Hammerspoon
scripts/setup-key.sh         store or replace the Keychain item
scripts/launch.sh            open Hammerspoon and reload
scripts/quit.sh              unload the assistant only
scripts/run.sh               the CLI the popup and the scripts call
scripts/test.sh              unit tests
scripts/test-connection.sh   one cheap text request
hammerspoon/mac_ai_assistant.lua
hammerspoon/popup.html       the floating window
python/assistant/cli.py      analyze, followup, test-connection, classes
python/assistant/client.py   Responses API requests and the tool loop
python/assistant/config.py   defaults and validation
python/assistant/secrets.py  environment, then Keychain
python/assistant/images.py   sips resize and cleanup
python/assistant/errors.py   codes and redaction
python/assistant/classes.py  class folder tools
python/assistant/library.py  the loopback classes site
python/assistant/practice.py practice-test format and grading
python/assistant/todo.py     due dates across classes
python/assistant/writing.py  My writing and the Write like me prompt
python/tests/                unittest modules
```

Hammerspoon logs to the “mac-ai-assistant” logger at info. It records that a request finished or the error code. It does not record the API key or the answer.

## Privacy

- Screenshots are written only to the temporary directory, resized there, and deleted after the request is prepared. They are not saved to the Desktop or Photos. Pass `--keep-image` only when you are debugging.
- The image is sent to OpenAI as part of the Responses API call. It is not sent to any other service. The client does not retry.
- Follow-up questions use OpenAI’s stored response id so the image does not have to be uploaded again. Your OpenAI account’s data-retention settings still apply. Closing the panel forgets the id locally. It does not delete the stored response on OpenAI’s side.
- The API key is not written to the popup, the Hammerspoon log, the config file, or this git repository. Displayed errors are scrubbed for key-shaped strings.
- Class files stay in the classes folder. The assistant cannot write outside that folder, and it will not follow a symlink out of it. When it reads a file to answer you, that text is included in the OpenAI request.
- My writing is included in full when you turn on **Write like me**, and when the model calls `read_my_writing`.
- The classes site listens on `127.0.0.1` only and does not log requests.

## What still has to be checked by hand

The popup, global shortcut, Screen Recording prompt, classes window in a real browser, and login item are not exercised by the automated tests. After `scripts/install.sh` and the permission prompts, confirm:

- Control-Option-] works while Safari, Chrome, or Preview is in front
- The panel stays at the upper-right of the display under the pointer, including on a second display
- The panel does not become the front application
- A second press during loading does not start another request
- A follow-up refers to the same screen
- The shortcut opens the panel and does not capture the screen
- **Add screenshot** captures the display under the pointer and does not include the popup
- Closing the panel ends the session, and the next message does not continue the old one
- **Classes** opens the browser page, **To-do** filters, and **Done** updates the list
- A practice test hides the answer until **Submit**
- **Write like me** fails with a clear message when My writing is empty, and includes the file when it is not
- An essay reply shows the comment in the chat and the writing in the plain text box
- `scripts/quit.sh` removes the AI menu until you reload Hammerspoon
