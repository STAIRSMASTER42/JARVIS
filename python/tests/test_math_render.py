"""Math rendering in the popup, exercised with macOS JavaScriptCore and KaTeX."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from assistant.cli import _local_context
from assistant.config import MATH_GUIDANCE, SYSTEM_INSTRUCTION, with_math_guidance


ROOT = Path(__file__).resolve().parents[2]
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc")
KATEX = ROOT / "hammerspoon" / "vendor" / "katex" / "katex.min.js"
RENDER = ROOT / "hammerspoon" / "render.js"
POPUP = ROOT / "hammerspoon" / "popup.html"
LUA = ROOT / "hammerspoon" / "mac_ai_assistant.lua"
FONTS = ROOT / "hammerspoon" / "vendor" / "katex" / "fonts"

_HARNESS = r"""
load(arguments[0]);
load(arguments[1]);
var katexLib = arguments[2] === "1" ? katex : null;
var html = jarvisRender.renderAssistantHtml(arguments[3], katexLib);
print("__JARVIS_RENDER_START__");
print(html);
print("__JARVIS_RENDER_END__");
"""


def render_html(text: str, *, katex: bool = True) -> str:
    if not JSC.is_file():
        raise unittest.SkipTest("JavaScriptCore is not available")
    completed = subprocess.run(
        [str(JSC), "-e", _HARNESS, "--", str(KATEX), str(RENDER), "1" if katex else "0", text],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    output = completed.stdout
    start = output.find("__JARVIS_RENDER_START__")
    end = output.find("__JARVIS_RENDER_END__")
    if start < 0 or end < start:
        raise AssertionError(output)
    return output[start + len("__JARVIS_RENDER_START__") : end].strip("\n")


class MathRenderTests(unittest.TestCase):
    def test_inline_and_display_delimiters(self) -> None:
        inline = render_html(r"Energy \(E=mc^2\) grows.")
        self.assertIn('class="math-scroll inline"', inline)
        self.assertIn("katex", inline)
        self.assertNotIn("katex-display", inline)
        self.assertIn("<p>", inline)
        self.assertNotIn(r"\(E=mc^2\)", inline)

        display = render_html("\\[\n\\int_0^1 x^2 \\, dx\n\\]")
        self.assertIn('class="math-scroll display"', display)
        self.assertIn("katex-display", display)
        self.assertIn("math-scroll", display)

        dollars = render_html("The root is $\\sqrt{x}$ today.")
        self.assertIn("math-scroll inline", dollars)
        self.assertIn("sqrt", dollars)

        doubled = render_html("$$\\frac{a}{b}$$")
        self.assertIn("math-scroll display", doubled)
        self.assertIn("mfrac", doubled)

    def test_common_notation(self) -> None:
        fraction = render_html(r"\(\frac{1}{2}\)")
        self.assertIn("mfrac", fraction)
        power = render_html(r"\(e^{i\pi}\)")
        self.assertIn("msup", power)
        greek = render_html(r"\(\alpha + \beta\)")
        self.assertIn("katex", greek)
        self.assertNotIn(r"\alpha", greek)
        total = render_html(r"\[\sum_{i=1}^{n} i\]")
        self.assertIn("katex-display", total)
        matrix = render_html(r"\[\begin{pmatrix} a & b \\ c & d \end{pmatrix}\]")
        self.assertIn("mtable", matrix)
        self.assertNotIn("<script", matrix.lower())

    def test_markdown_survives_around_math(self) -> None:
        html = render_html("**Force**\n\n# Motion\n\n- mass \\(m\\)\n- acceleration")
        self.assertIn("<strong>Force</strong>", html)
        self.assertIn("<h1>Motion</h1>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<li>mass ", html)
        self.assertIn("math-scroll inline", html)
        self.assertIn("<li>acceleration</li>", html)

    def test_code_is_not_rendered_as_math(self) -> None:
        fenced = render_html("Use this\n\n```tex\n\\(x^2\\)\n$$\n\\alpha\n```\n\nDone \\(y\\)")
        code, _, rest = fenced.partition("</code></pre>")
        self.assertIn(r"\(x^2\)", code)
        self.assertIn("$$", code)
        self.assertNotIn("katex", code)
        self.assertIn("math-scroll inline", rest)
        inline = render_html(r"Type `\(x^2\)` and then \(y\).")
        self.assertIn("<code>\\(x^2\\)</code>", inline)
        self.assertEqual(inline.count("math-scroll"), 1)

    def test_untrusted_html_is_escaped(self) -> None:
        html = render_html('<script>alert(1)</script>\n<img src=x onerror="alert(1)">')
        self.assertNotRegex(html, r"<\s*script\b")
        self.assertNotRegex(html, r"<\s*img\b")
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", html)
        link = render_html(r"\(\href{javascript:alert(1)}{click}\)")
        self.assertNotRegex(link, r"<\s*a\b")
        self.assertNotRegex(link, r"javascript\s*:")
        self.assertNotIn("<script", link.lower())

    def test_currency_and_unclosed_dollars_stay_text(self) -> None:
        html = render_html("It costs $5 and $10 today.")
        self.assertNotIn("katex", html)
        self.assertIn("$5", html)
        self.assertIn("$10", html)
        bare = render_html(r"Leave \(this unclosed")
        self.assertNotIn("katex", bare)
        self.assertIn("\\(", bare)

    def test_missing_katex_falls_back_to_escaped_text(self) -> None:
        html = render_html(r"See \(x^2\) <b>now</b>", katex=False)
        self.assertNotIn("katex", html)
        self.assertIn("\\(x^2\\)", html)
        self.assertIn("&lt;b&gt;", html)

    def test_math_guidance_is_sent_with_requests(self) -> None:
        self.assertIn(r"\(", SYSTEM_INSTRUCTION)
        self.assertIn(r"\[", SYSTEM_INSTRUCTION)
        self.assertIn("Do not use dollar signs for math.", SYSTEM_INSTRUCTION)
        self.assertEqual(with_math_guidance(SYSTEM_INSTRUCTION), SYSTEM_INSTRUCTION)
        older = with_math_guidance("Be Jarvis.")
        self.assertTrue(older.startswith("Be Jarvis."))
        self.assertIn(MATH_GUIDANCE, older)
        self.assertEqual(with_math_guidance(older).count(MATH_GUIDANCE), 1)
        instructions, tools, _execute = _local_context({"system_instruction": "Be Jarvis."}, None)
        self.assertIsNone(tools)
        self.assertIn(r"\(", instructions)

    def test_popup_bundles_katex_for_every_answer(self) -> None:
        popup = POPUP.read_text(encoding="utf-8")
        lua = LUA.read_text(encoding="utf-8")
        self.assertIn("vendor/katex/katex.min.css", popup)
        self.assertIn("vendor/katex/katex.min.js", popup)
        self.assertIn("render.js", popup)
        self.assertIn("jarvisRender.renderAssistantHtml", popup)
        self.assertIn("showAnswer", popup)
        self.assertIn("inlineMathAssets", lua)
        self.assertIn("data:font/woff2;base64,", lua)
        self.assertIn("view:html(html)", lua)
        css = (ROOT / "hammerspoon" / "vendor" / "katex" / "katex.min.css").read_text(encoding="utf-8")
        names = set(re.findall(r"url\(fonts/([^)]+\.woff2)\)", css))
        self.assertGreaterEqual(len(names), 10)
        missing = [name for name in names if not (FONTS / name).is_file()]
        self.assertEqual(missing, [])
        self.assertTrue((ROOT / "hammerspoon" / "vendor" / "katex" / "LICENSE").is_file())
