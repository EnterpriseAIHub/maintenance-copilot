"""Chunking.

Structure-aware where headings are detectable (groups paragraphs under
their nearest preceding heading so a chunk's `section_title` is
meaningful), falling back to plain token-window packing otherwise. Per
EDD §13/§20, target ~400-600 tokens with ~15% overlap between consecutive
chunks so a fact near a chunk boundary isn't invisible to retrieval.

Token counting is a cheap character-based approximation
(`estimate_token_count`), not an exact tokenizer (e.g. tiktoken) — an
exact tokenizer's BPE rank files are normally downloaded from an external
host on first use, which would make this repo's ingestion pipeline depend
on network access to a domain outside this project's control, contradicting
NFR7 (no hidden external dependencies). The approximation is documented
here and swappable behind this one function if precise token budgets ever
become necessary (e.g. approaching a provider's exact context-window
limit).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.extractors import ExtractedPage

DEFAULT_TARGET_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 75
_CHARS_PER_TOKEN = 4  # rough English-text approximation

_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")
_NUMBERED_HEADING = re.compile(r"^\d+(\.\d+){0,3}\s+[A-Z].{0,78}$")
_ALL_CAPS_HEADING = re.compile(r"^[A-Z0-9][A-Z0-9 ,\-/&]{2,78}$")


@dataclass(frozen=True)
class ChunkCandidate:
    text: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    token_count: int


def estimate_token_count(text: str) -> int:
    """Cheap, dependency-free token estimate. See module docstring."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 80:
        return False
    if _MARKDOWN_HEADING.match(line):
        return True
    if _NUMBERED_HEADING.match(line):
        return True
    if _ALL_CAPS_HEADING.match(line) and not line.isdigit() and any(c.isalpha() for c in line):
        return True
    return False


def _split_paragraphs(page: ExtractedPage) -> list[tuple[int | None, str, bool]]:
    """Splits a page's text into (page_number, paragraph, is_heading) tuples."""
    paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]
    result = []
    for paragraph in paragraphs:
        first_line = paragraph.splitlines()[0] if paragraph else ""
        is_heading = len(paragraph.splitlines()) == 1 and _is_heading(first_line)
        result.append((page.page_number, paragraph, is_heading))
    return result


def _split_oversized_paragraph(paragraph: str, target_tokens: int) -> list[str]:
    """Sentence-splits a single paragraph that alone exceeds the target
    chunk size, so one huge unbroken block of text doesn't become one huge
    unbroken chunk.
    """
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip()
        if buffer and estimate_token_count(candidate) > target_tokens:
            pieces.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        pieces.append(buffer)
    return pieces or [paragraph]


def chunk_pages(
    pages: list[ExtractedPage],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkCandidate]:
    """Chunks cleaned page text into overlapping, section-aware chunks."""
    units: list[tuple[int | None, str, bool]] = []
    for page in pages:
        units.extend(_split_paragraphs(page))

    chunks: list[ChunkCandidate] = []
    buffer_parts: list[str] = []
    buffer_page: int | None = None
    current_section: str | None = None

    def flush() -> None:
        if not buffer_parts:
            return
        text = "\n\n".join(buffer_parts).strip()
        if not text:
            return
        chunks.append(
            ChunkCandidate(
                text=text,
                chunk_index=len(chunks),
                page_number=buffer_page,
                section_title=current_section,
                token_count=estimate_token_count(text),
            )
        )

    for page_number, paragraph, is_heading in units:
        if is_heading:
            # Headings update the running section title but aren't chunked
            # as content themselves — they're metadata, not evidence a
            # citation should point at.
            current_section = paragraph
            continue

        candidate_parts = [*buffer_parts, paragraph]
        candidate_text = "\n\n".join(candidate_parts)

        if estimate_token_count(candidate_text) <= target_tokens:
            buffer_parts = candidate_parts
            if buffer_page is None:
                buffer_page = page_number
            continue

        # Adding this paragraph would exceed the target — close the
        # current chunk first.
        if buffer_parts:
            flush()
            overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
            tail = "\n\n".join(buffer_parts)[-overlap_chars:]
            buffer_parts = [tail] if tail else []
            buffer_page = page_number

        if estimate_token_count(paragraph) > target_tokens:
            # A single paragraph too large to fit even in an empty chunk —
            # sub-split it by sentence rather than emitting one oversized
            # chunk.
            for piece in _split_oversized_paragraph(paragraph, target_tokens):
                buffer_parts.append(piece)
                if estimate_token_count("\n\n".join(buffer_parts)) > target_tokens:
                    flush()
                    buffer_parts = []
                    buffer_page = page_number
        else:
            buffer_parts.append(paragraph)

    flush()
    return chunks
