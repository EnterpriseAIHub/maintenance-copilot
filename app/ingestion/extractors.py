"""Text extraction.

Core scope for Phase 2 is native text extraction only (PDF, DOCX) — no
OCR. This is a deliberate scoping choice, not an oversight: the seed
corpus is curated to be born-digital (see EDD §20 / PROJECT_PROGRESS.md),
so a scanned-document fallback isn't needed yet. If real scanned legacy
manuals ever enter the corpus, an OCR extractor slots in here behind the
same ExtractedPage interface without touching chunking/embedding.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import docx
from pypdf import PdfReader

from app.services.errors import UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


@dataclass(frozen=True)
class ExtractedPage:
    """One page of extracted text.

    `page_number` is None for formats without a native page concept
    (DOCX) — citations for chunks from such documents simply omit a page
    number rather than fabricating one.
    """

    page_number: int | None
    text: str


def extract_pages(file_bytes: bytes, filename: str) -> list[ExtractedPage]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_bytes)
    if suffix == ".docx":
        return _extract_docx(file_bytes)
    raise UnsupportedFileTypeError(
        f"Unsupported file type: '{suffix}'. Supported types: {sorted(SUPPORTED_EXTENSIONS)}",
        detail={"filename": filename, "extension": suffix},
    )


def _extract_pdf(file_bytes: bytes) -> list[ExtractedPage]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(ExtractedPage(page_number=index, text=text))
    return pages


def _extract_docx(file_bytes: bytes) -> list[ExtractedPage]:
    document = docx.Document(io.BytesIO(file_bytes))
    text = "\n\n".join(paragraph.text for paragraph in document.paragraphs)
    return [ExtractedPage(page_number=None, text=text)]
