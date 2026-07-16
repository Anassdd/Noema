"""Shared adapter helpers: HTML -> plain text, token-capped prefixes, atomic writes."""

from __future__ import annotations

import html as html_lib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import tiktoken


def write_json_atomic(data, out_path) -> None:
    """Never leave a half-written dataset file — write beside, then swap in."""
    out = Path(out_path)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    tmp.replace(out)

_ENC = tiktoken.get_encoding("o200k_base")
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table",
               "section", "article", "ul", "ol"}
_SCRIPT_RE = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1\s*>", re.I | re.S)
_BLOCK_RE = re.compile(r"</?(?:p|div|br|li|tr|h[1-6]|table|section|article|ul|ol)[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(fragment: str) -> str:
    """Small fragments (a provision, an FAQ) -> clean text, block tags to newlines."""
    text = _SCRIPT_RE.sub(" ", fragment or "")
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)


def page_to_text(html: str) -> str:
    """Whole web pages (arbitrarily messy) -> plain text via a real parser."""
    p = _TextExtractor()
    try:
        p.feed(html or "")
    except Exception:
        pass
    text = re.sub(r"[ \t]+", " ", "".join(p.parts))
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def cap_tokens(text: str, budget: int) -> tuple[str, int]:
    """Line-aligned prefix of `text` within `budget` tokens; returns (text, tokens)."""
    ids = _ENC.encode(text, disallowed_special=())
    if len(ids) <= budget:
        return text, len(ids)
    out, used = [], 0
    for line in text.split("\n"):
        t = len(_ENC.encode(line + "\n", disallowed_special=()))
        if out and used + t > budget:
            break
        out.append(line)
        used += t
    return "\n".join(out), used


_BINARY = {"is", "are", "am", "was", "were", "do", "does", "did", "can", "could",
           "should", "shall", "must", "may", "might", "will", "would", "has", "have", "had"}
_WH = {"what", "which", "when", "where", "who", "whom", "whose", "why"}
_CONDITIONAL = {"if", "in", "as", "assuming", "given", "suppose"}


def question_form(question: str) -> str:
    """Surface-form question type: binary | wh | how | conditional | other."""
    words = re.findall(r"[a-z']+", question.lower())
    if not words:
        return "other"
    first = words[0]
    if first in _BINARY:
        return "binary"
    if first == "how":
        return "how"
    if first in _WH:
        return "wh"
    if first in _CONDITIONAL:
        return "conditional"
    return "other"
