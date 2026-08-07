from __future__ import annotations

from app.ingestion.cleaning import clean_text


def test_collapses_repeated_whitespace() -> None:
    assert clean_text("hello    world") == "hello world"


def test_collapses_excess_blank_lines() -> None:
    assert clean_text("para one\n\n\n\n\npara two") == "para one\n\npara two"


def test_dehyphenates_line_wrapped_words() -> None:
    assert clean_text("main-\ntenance schedule") == "maintenance schedule"


def test_strips_standalone_page_number_lines() -> None:
    text = "Section content here.\n42\nMore content."
    cleaned = clean_text(text)
    assert "42" not in cleaned.split("\n")


def test_normalizes_windows_line_endings() -> None:
    assert clean_text("line one\r\nline two") == "line one\nline two"


def test_empty_input_returns_empty_string() -> None:
    assert clean_text("") == ""
