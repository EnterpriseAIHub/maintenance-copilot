from __future__ import annotations

from app.ingestion.chunking import chunk_pages, estimate_token_count
from app.ingestion.extractors import ExtractedPage


def test_short_document_produces_single_chunk() -> None:
    pages = [ExtractedPage(page_number=1, text="A short paragraph about a pump.")]

    chunks = chunk_pages(pages, target_tokens=500)

    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0


def test_heading_is_tracked_as_section_title_not_emitted_as_a_chunk() -> None:
    pages = [
        ExtractedPage(
            page_number=1,
            text="TROUBLESHOOTING VIBRATION\n\nCheck bearing alignment first.",
        )
    ]

    chunks = chunk_pages(pages, target_tokens=500)

    assert len(chunks) == 1
    assert chunks[0].section_title == "TROUBLESHOOTING VIBRATION"
    assert "TROUBLESHOOTING VIBRATION" not in chunks[0].text


def test_long_document_splits_into_multiple_chunks_with_sequential_index() -> None:
    # Each paragraph is ~30 tokens; with a small target, this should split.
    paragraph = "This paragraph describes a maintenance procedure in some detail. " * 5
    pages = [ExtractedPage(page_number=1, text="\n\n".join([paragraph] * 10))]

    chunks = chunk_pages(pages, target_tokens=100, overlap_tokens=20)

    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        # Some slack above target_tokens is expected because the overlap
        # tail plus one more paragraph can push a chunk slightly over
        # before the next flush.
        assert chunk.token_count <= 250


def test_oversized_single_paragraph_is_sentence_split() -> None:
    long_paragraph = "This is one sentence about the equipment. " * 60
    pages = [ExtractedPage(page_number=1, text=long_paragraph)]

    chunks = chunk_pages(pages, target_tokens=100)

    assert len(chunks) > 1


def test_multi_page_document_preserves_starting_page_number() -> None:
    pages = [
        ExtractedPage(page_number=1, text="Content from page one."),
        ExtractedPage(page_number=2, text="Content from page two."),
    ]

    chunks = chunk_pages(pages, target_tokens=500)

    # Small enough to fit in one chunk together; the chunk should be
    # attributed to the first page it drew content from.
    assert chunks[0].page_number == 1


def test_docx_pages_with_no_page_number_are_handled() -> None:
    pages = [ExtractedPage(page_number=None, text="DOCX has no native page concept.")]

    chunks = chunk_pages(pages, target_tokens=500)

    assert chunks[0].page_number is None


def test_estimate_token_count_is_never_zero_for_nonempty_text() -> None:
    assert estimate_token_count("hi") >= 1


def test_empty_pages_produce_no_chunks() -> None:
    assert chunk_pages([]) == []


def test_merged_chunk_keeps_first_sections_heading_not_a_later_one() -> None:
    # Two short sections that together still fit under target_tokens get
    # packed into a single chunk. Regression test for a labeling bug where
    # flush() used whatever heading was *most recently seen* (SAFETY
    # PRECAUTIONS) rather than the heading in effect when this chunk's
    # content actually started accumulating (OVERVIEW).
    text = (
        "OVERVIEW\n\n"
        "Short intro paragraph about the equipment.\n\n"
        "SAFETY PRECAUTIONS\n\n"
        "Short paragraph about lockout tagout."
    )
    pages = [ExtractedPage(page_number=1, text=text)]

    chunks = chunk_pages(pages, target_tokens=500)

    assert len(chunks) == 1
    assert chunks[0].section_title == "OVERVIEW"


def test_section_boundary_forces_correct_label_on_each_side() -> None:
    # When the combined content of two sections *doesn't* fit in one
    # chunk, each resulting chunk should be labeled with the heading that
    # was active when its own content started, not a heading from later
    # in the document.
    para_a = "Sentence about section A. " * 20
    para_b = "Sentence about section B. " * 20
    text = f"SECTION A HEADING\n\n{para_a}\n\nSECTION B HEADING\n\n{para_b}"
    pages = [ExtractedPage(page_number=1, text=text)]

    chunks = chunk_pages(pages, target_tokens=100, overlap_tokens=10)

    assert len(chunks) >= 2
    assert chunks[0].section_title == "SECTION A HEADING"
    assert chunks[-1].section_title == "SECTION B HEADING"
