"""Split extracted text into overlapping chunks sized for embedding and retrieval."""

import re

CHUNK_SIZE = 1000  # target characters per chunk
CHUNK_OVERLAP = 150  # characters repeated at the start of the next chunk

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_long(piece: str, size: int) -> list[str]:
    """Break a paragraph longer than `size` at sentence ends, then at spaces,
    then (for unbroken text) at exactly `size` characters."""
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(piece):
        while len(sentence) > size:
            cut = sentence.rfind(" ", 0, size)
            cut = cut if cut > 0 else size
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > size:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return [p for p in parts if p]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Paragraph-aware chunks of at most roughly `size` characters.

    Paragraphs are packed together until a chunk is full; each new chunk starts
    with the tail of the previous one so a fact straddling a boundary is still
    found whole in at least one chunk.
    """
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and smaller than size")

    pieces: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pieces.extend(_split_long(paragraph, size) if len(paragraph) > size else [paragraph])

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) > size:
            chunks.append(current)
            tail = current[-overlap:].lstrip() if overlap else ""
            current = f"{tail}\n\n{piece}" if tail else piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
