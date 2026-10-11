# macOS AI Screen Assistant

A menu-bar assistant for macOS. Press **Control + Option + ]** and it captures the display you are using, sends that one screenshot to the OpenAI Responses API, and shows the answer in a small floating window at the upper-right of that display.

It does not watch the screen in the background. A capture happens only when you press the shortcut or choose **Ask about this screen** from the **AI** menu.

## How it is put together

Hammerspoon listens for the shortcut and draws the popup. A Python virtualenv in this project sends the image to OpenAI. Your API key stays in the macOS Keychain (or in `OPENAI_API_KEY`) and is never written into this repository.

```
Control-Option-]
  → Hammerspoon captures the display under the pointer
  → scripts/run.sh  (background task, the popup stays responsive)
  → OpenAI Responses API
  → floating panel on the same display
```

Follow-up questions stay in that popup and reuse the same response, so the screenshot is not sent again. Closing the panel or taking a new screenshot starts a new session.

## Install on this Mac or another Mac

Requirements:

- macOS 13 or newer
- [Homebrew](https://brew.sh)
- Python 3.10 or newer (the installer uses Homebrew’s Python 3.12 when the system Python is older)
- An OpenAI API key with access to a vision model

```bash
git clone <this-repo> ~/Projects/mac-ai-assistant
cd ~/Projects/mac-ai-assistant
scripts/install.sh
```

The installer:

- Installs Hammerspoon if it is missing
- Creates `.venv` and installs `requirements.txt`
- Copies `config.example.json` to `~/.config/mac-ai-assistant/config.json` if you do not already have one
- Asks for an API key and stores it in Keychain
- Loads the assistant from `~/.hammerspoon/init.lua` without removing other Hammerspoon config
- Opens Hammerspoon at login

Run `scripts/install.sh --yes` to skip the key prompt (useful if `OPENAI_API_KEY` is already set, or if you will run `scripts/setup-key.sh` afterward).

### API key

Each Mac has its own key. The installer stores it with:

```bash
scripts/setup-key.sh
```

That writes a Keychain item named `mac-ai-assistant` / `openai`. You can instead export `OPENAI_API_KEY` in the environment Hammerspoon can see. The environment variable is checked first. Do not put the key in `config.json` or in git.

The first request may show a Keychain prompt for `python`. Choose **Always Allow**.

### Permissions

macOS will not grant these until you approve them:

| Permission | Why | Where |
|---|---|---|
| Accessibility | The shortcut must work while another app is focused | System Settings → Privacy & Security → Accessibility → Hammerspoon |
| Screen Recording | Capture the display | System Settings → Privacy & Security → Screen Recording → Hammerspoon |
| Keychain | Read the API key | Prompt on the first request |

After changing Screen Recording, quit Hammerspoon and open it again. A denied capture shows the same instructions in the popup.

The panel uses a non-activating window so it can appear over Safari, Chrome, Preview, or the desktop without becoming the front application. Confirm that on your Mac after install; window focus behavior depends on Hammerspoon.

## Use it

1. Run `scripts/launch.sh` (or open Hammerspoon and choose **Reload Config**).
2. An **AI** item appears in the menu bar.
3. Press **Control + Option + ]**.

The popup shows a spinner, then the answer. Text in the answer can be selected. **Copy** puts the conversation on the clipboard. Drag the title bar to move the panel. **Close** or **Escape** dismisses it.

Pressing the shortcut again while a request is running does not start a second request.

Type a follow-up in the box at the bottom and press Return. That conversation lasts until you close the panel or capture a new screen.

### Quit or disable

- Menu bar **AI → Disable shortcut** leaves the assistant loaded but ignores the hotkey. **Enable shortcut** turns it back on. The menu item **Ask about this screen** still works while the hotkey is disabled.
- **AI → Quit Screen Assistant** unloads the hotkey, menu item, and popup. Other Hammerspoon config keeps running.
- From a terminal: `scripts/quit.sh`
- To start it again: `scripts/launch.sh`
- To stop it opening at login, disable **Launch Hammerspoon at login** in Hammerspoon’s preferences, or remove the Hammerspoon login item.

## Configuration

Edit `~/.config/mac-ai-assistant/config.json`, then choose **Reload Config** from the AI menu (or run `scripts/launch.sh`).

| Field | Purpose |
|---|---|
| `shortcut.modifiers` / `shortcut.key` | Global hotkey. Default is `ctrl`, `alt`, and `]`. |
| `model` | Vision-capable model. Default is `gpt-5.4-mini`. |
| `system_instruction` | Instruction sent with every request. |
| `max_output_tokens` | Cap on the answer length. Default `800`. |
| `image_max_edge` | Longest side of the JPEG sent to the API, in pixels. Default `1600`. |
| `jpeg_quality` | JPEG quality from 40 to 95. Default `80`. |
| `image_detail` | `low`, `high`, `auto`, or `original`. Default `high`, so small text stays readable. |
| `timeout_seconds` | Request timeout. Default `45`. |
| `popup.width`, `popup.max_height`, `popup.margin` | Size and inset of the panel. |

The initial instruction asks the model to answer a visible question, name a multiple-choice answer by letter and text, or summarize reading material, and not to invent details that are not on screen.

## Check the API

This sends a short text request (no screenshot) and prints JSON. It uses a small amount of API credit:

```bash
scripts/test-connection.sh
```

A working key looks like `{"ok": true, "text": "ok", ...}`. Failures use the same messages as the popup: missing key, rejected key, billing or quota, network, or timeout.

## Tests

Unit tests cover config parsing, error mapping, Keychain lookup (the `security` tool is mocked), request payloads, screenshot cleanup, and the CLI. They do not call OpenAI and do not open a window.

```bash
scripts/test.sh
```

## Privacy

- Screenshots are written only to the temporary directory, resized there, and deleted after the request is prepared. They are not saved to the Desktop or Photos.
- The image is sent to OpenAI as part of the Responses API call. It is not sent to any other service.
- Follow-up questions use OpenAI’s stored response id so the image does not have to be uploaded again. Your OpenAI account’s data-retention settings still apply.
- The API key is not written to the popup, the Hammerspoon log, or this git repository.

## What still has to be checked by hand

The popup, global shortcut, Screen Recording prompt, and login item were not exercised from the automated tests. After `scripts/install.sh` and the permission prompts, confirm:

- Control-Option-] works while Safari, Chrome, or Preview is in front
- The panel stays at the upper-right of the display under the pointer
- A second press during loading does not start another request
- A follow-up refers to the same screen
- Closing the panel and pressing the shortcut starts a fresh answer
- `scripts/quit.sh` removes the AI menu until you reload Hammerspoon
