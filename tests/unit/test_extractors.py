"""Extractor tests use in-memory generated fixtures (fpdf2 for PDF,
python-docx for DOCX) rather than committed binary sample files, so the
test suite doesn't depend on binary fixtures living in version control.
"""

from __future__ import annotations

import io

import docx
import pytest
from fpdf import FPDF

from app.ingestion.extractors import extract_pages
from app.services.errors import UnsupportedFileTypeError


def _make_pdf_bytes(pages_text: list[str]) -> bytes:
    pdf = FPDF()
    for text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_pdf_extraction_returns_one_page_per_pdf_page_with_text() -> None:
    pdf_bytes = _make_pdf_bytes(["First page content.", "Second page content."])

    pages = extract_pages(pdf_bytes, "manual.pdf")

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert "First page content" in pages[0].text
    assert pages[1].page_number == 2
    assert "Second page content" in pages[1].text


def test_docx_extraction_returns_single_page_with_no_page_number() -> None:
    docx_bytes = _make_docx_bytes(["Paragraph one.", "Paragraph two."])

    pages = extract_pages(docx_bytes, "sop.docx")

    assert len(pages) == 1
    assert pages[0].page_number is None
    assert "Paragraph one." in pages[0].text
    assert "Paragraph two." in pages[0].text


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        extract_pages(b"not a real file", "notes.txt")
