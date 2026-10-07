import pytest

from app.documents.chunking import chunk_text


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Hello world.") == ["Hello world."]


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("  \n\n  ") == []


def test_paragraphs_are_packed_and_chunks_are_bounded() -> None:
    text = "\n\n".join(f"Paragraph number {i} " + "word " * 40 for i in range(30))

    chunks = chunk_text(text, size=500, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 500 + 50 + 2 for c in chunks)
    # nothing is lost: every paragraph appears in some chunk
    for i in range(30):
        assert any(f"Paragraph number {i} " in c for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    text = "\n\n".join(f"unique{i} " + "filler " * 30 for i in range(10))

    chunks = chunk_text(text, size=400, overlap=60)

    for previous, current in zip(chunks, chunks[1:]):
        assert previous[-30:] in current


def test_one_huge_paragraph_is_split() -> None:
    sentence = "This is a sentence about something. "
    chunks = chunk_text(sentence * 200, size=300, overlap=0)

    assert len(chunks) > 10
    assert all(len(c) <= 300 for c in chunks)


def test_unbroken_text_is_split_hard() -> None:
    chunks = chunk_text("x" * 2500, size=1000, overlap=0)

    assert [len(c) for c in chunks] == [1000, 1000, 500]


def test_invalid_overlap_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=100, overlap=100)
