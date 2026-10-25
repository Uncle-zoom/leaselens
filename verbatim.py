"""Insert the author's own text files into the report WITHOUT changing a word.

Only structure is translated (# headings, - bullets, paragraphs). Every character of the text is kept (HTML-escaped); a "(TO ADD ...)" note is
shown as a small grey note with its text unchanged. Nothing is added, summarised or rephrased.
"""
from __future__ import annotations

import html
import re

NOTE = re.compile(r"\(TO ADD.*?\)", re.S)


def inline(text: str) -> str:
    out, pos = [], 0
    for m in NOTE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        out.append(f'<span class="note">{html.escape(m.group(0))}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def render(text: str, heading_base: int = 3) -> str:
    """Markdown subset used by content/*.md: '# ' and '## ' headings, '- ' bullets (with indented continuation lines), paragraphs."""
    html_parts: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        h = re.match(r"(#{1,3}) (.*)", line)
        if h:
            level = min(6, heading_base + len(h.group(1)) - 1)
            html_parts.append(f"<h{level}>{inline(h.group(2))}</h{level}>")
            i += 1
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                chunk = [lines[i][2:]]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    chunk.append(lines[i].strip())
                    i += 1
                items.append("<li>" + inline("\n".join(chunk)) + "</li>")
            html_parts.append("<ul>" + "".join(items) + "</ul>")
        else:
            chunk = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "- ")):
                chunk.append(lines[i])
                i += 1
            html_parts.append("<p>" + inline("\n".join(chunk)) + "</p>")
    return "\n".join(html_parts)


def plain(text: str) -> str:
    """The text as a reader sees it: markdown markers removed, whitespace collapsed. Used to prove an insertion is verbatim."""
    t = re.sub(r"(?m)^#{1,3} ", "", text)
    t = re.sub(r"(?m)^- ", "", t)
    return re.sub(r"\s+", " ", t).strip()


def visible(html_text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()
