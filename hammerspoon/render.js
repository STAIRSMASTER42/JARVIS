/* Renders assistant text to HTML.
   Code is left as text. Math outside code is drawn with KaTeX.
   The input is untrusted: text is escaped, and KaTeX output is rejected
   if it contains markup that could run script. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.jarvisRender = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function unsafeMath(html) {
    return /<\s*script\b|<\s*iframe\b|<\s*object\b|<\s*embed\b|<\s*link\b|<\s*meta\b|javascript\s*:|data\s*:\s*text\/html|on[a-z]+\s*=/i.test(html);
  }

  function renderMath(latex, display, katexLib, original) {
    var cleaned = String(latex || "").trim();
    if (!cleaned || !katexLib || typeof katexLib.renderToString !== "function") {
      return escapeHtml(original);
    }
    var html;
    try {
      html = katexLib.renderToString(cleaned, {
        displayMode: !!display,
        throwOnError: false,
        trust: false,
        strict: "ignore",
        output: "html",
      });
    } catch (err) {
      return escapeHtml(original);
    }
    if (typeof html !== "string" || unsafeMath(html)) {
      return escapeHtml(original);
    }
    var kind = display ? "math-scroll display" : "math-scroll inline";
    return '<span class="' + kind + '">' + html + "</span>";
  }

  function stash(slots, html, display) {
    var token = "\u0000" + (display ? "D" : "S") + String(slots.length) + "\u0000";
    slots.push(html);
    return token;
  }

  function findClosingDollar(text, start) {
    if (start >= text.length || /\s/.test(text.charAt(start))) {
      return -1;
    }
    var i = start;
    while (i < text.length) {
      var ch = text.charAt(i);
      if (ch === "\n") {
        return -1;
      }
      if (ch === "\\") {
        i += 2;
        continue;
      }
      if (ch === "$") {
        if (text.charAt(i + 1) === "$") {
          return -1;
        }
        var content = text.slice(start, i);
        if (!content || /\s$/.test(content)) {
          return -1;
        }
        return i;
      }
      i += 1;
    }
    return -1;
  }

  function shield(raw, katexLib) {
    var slots = [];
    var out = "";
    var i = 0;
    while (i < raw.length) {
      var rest = raw.slice(i);
      if (raw.charAt(i) === "`") {
        var endCode = raw.indexOf("`", i + 1);
        var newline = raw.indexOf("\n", i + 1);
        if (endCode > i + 1 && (newline === -1 || endCode < newline)) {
          out += stash(slots, "<code>" + escapeHtml(raw.slice(i + 1, endCode)) + "</code>", false);
          i = endCode + 1;
          continue;
        }
      }
      if (rest.indexOf("$$") === 0) {
        var endDisplay = raw.indexOf("$$", i + 2);
        if (endDisplay !== -1) {
          out += stash(
            slots,
            renderMath(raw.slice(i + 2, endDisplay), true, katexLib, raw.slice(i, endDisplay + 2)),
            true
          );
          i = endDisplay + 2;
          continue;
        }
      }
      if (rest.indexOf("\\[") === 0) {
        var endBracket = raw.indexOf("\\]", i + 2);
        if (endBracket !== -1) {
          out += stash(
            slots,
            renderMath(raw.slice(i + 2, endBracket), true, katexLib, raw.slice(i, endBracket + 2)),
            true
          );
          i = endBracket + 2;
          continue;
        }
      }
      if (rest.indexOf("\\(") === 0) {
        var endParen = raw.indexOf("\\)", i + 2);
        if (endParen !== -1) {
          out += stash(
            slots,
            renderMath(raw.slice(i + 2, endParen), false, katexLib, raw.slice(i, endParen + 2)),
            false
          );
          i = endParen + 2;
          continue;
        }
      }
      if (raw.charAt(i) === "$" && raw.charAt(i + 1) !== "$" && (i === 0 || raw.charAt(i - 1) !== "\\")) {
        var endDollar = findClosingDollar(raw, i + 1);
        if (endDollar !== -1) {
          out += stash(
            slots,
            renderMath(raw.slice(i + 1, endDollar), false, katexLib, raw.slice(i, endDollar + 1)),
            false
          );
          i = endDollar + 1;
          continue;
        }
      }
      out += raw.charAt(i);
      i += 1;
    }
    return { text: out, slots: slots };
  }

  function formatInline(line, slots) {
    var html = "";
    var i = 0;
    var bold = false;
    while (i < line.length) {
      if (line.indexOf("**", i) === i) {
        var closer = line.indexOf("**", i + 2);
        if (!bold && closer === -1) {
          html += escapeHtml("**");
          i += 2;
          continue;
        }
        html += bold ? "</strong>" : "<strong>";
        bold = !bold;
        i += 2;
        continue;
      }
      if (line.charCodeAt(i) === 0) {
        var match = /^\u0000[SD](\d+)\u0000/.exec(line.slice(i));
        if (match) {
          html += slots[Number(match[1])] || "";
          i += match[0].length;
          continue;
        }
      }
      var j = i;
      while (j < line.length && line.indexOf("**", j) !== j && line.charCodeAt(j) !== 0) {
        j += 1;
      }
      html += escapeHtml(line.slice(i, j));
      i = j;
    }
    if (bold) {
      html += "</strong>";
    }
    return html;
  }

  function formatProse(raw, katexLib) {
    var shielded = shield(raw, katexLib);
    var lines = shielded.text.split("\n");
    var html = "";
    var listOpen = false;
    function closeList() {
      if (listOpen) {
        html += "</ul>";
        listOpen = false;
      }
    }
    lines.forEach(function (line) {
      var displayOnly = /^\s*\u0000D(\d+)\u0000\s*$/.exec(line);
      if (displayOnly) {
        closeList();
        html += shielded.slots[Number(displayOnly[1])] || "";
        return;
      }
      var heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) {
        closeList();
        var level = heading[1].length;
        html += "<h" + level + ">" + formatInline(heading[2], shielded.slots) + "</h" + level + ">";
        return;
      }
      var item = /^\s*[-*]\s+(.*)$/.exec(line);
      if (item) {
        if (!listOpen) {
          html += "<ul>";
          listOpen = true;
        }
        html += "<li>" + formatInline(item[1], shielded.slots) + "</li>";
        return;
      }
      closeList();
      if (line.trim() !== "") {
        html += "<p>" + formatInline(line, shielded.slots) + "</p>";
      }
    });
    closeList();
    return html;
  }

  function renderAssistantHtml(text, katexLib) {
    var source = String(text == null ? "" : text).replace(/\u0000/g, "");
    var chunks = source.split("```");
    var html = "";
    var index;
    for (index = 0; index < chunks.length; index += 1) {
      if (index % 2 === 1) {
        var code = chunks[index].replace(/^[^\n]*\n/, "");
        html += "<pre><code>" + escapeHtml(code) + "</code></pre>";
        continue;
      }
      html += formatProse(chunks[index], katexLib);
    }
    return html;
  }

  return { renderAssistantHtml: renderAssistantHtml, escapeHtml: escapeHtml };
});
