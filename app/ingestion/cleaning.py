"""Text cleaning.

Normalizes extraction artifacts before chunking: line-ending
normalization, whitespace collapsing, de-hyphenation of line-wrapped
words, and removal of standalone page-number footer/header lines.
Deliberately simple, regex-based heuristics — sufficient for the manuals
this repo targets, not a general-purpose document-cleaning library.
"""

from __future__ import annotations

import re

_REPEATED_WHITESPACE = re.compile(r"[ \t]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_LINE_WRAPPED_HYPHEN = re.compile(r"(\w+)-\n(\w+)")
_STANDALONE_PAGE_NUMBER_LINE = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _LINE_WRAPPED_HYPHEN.sub(r"\1\2", text)
    text = _STANDALONE_PAGE_NUMBER_LINE.sub("", text)
    text = _REPEATED_WHITESPACE.sub(" ", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)

    return text.strip()
