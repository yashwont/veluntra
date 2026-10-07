import io

import pytest
from docx import Document as DocxDocument

from app.documents.extract import (
    ExtractionError,
    UnsupportedFileTypeError,
    detect_type,
    extract_text,
)


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF whose page shows `text` (readers rebuild the xref)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def make_docx(*paragraphs: str, table: list[list[str]] | None = None) -> bytes:
    doc = DocxDocument()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_plain_text_and_markdown() -> None:
    assert extract_text("a.txt", b"hello there\n") == "hello there"
    assert extract_text("a.md", "# Title\n\nbody".encode()) == "# Title\n\nbody"


def test_utf8_bom_is_stripped_and_latin1_falls_back() -> None:
    assert extract_text("a.txt", b"\xef\xbb\xbfhi") == "hi"
    assert extract_text("a.txt", "café".encode("latin-1")) == "café"


def test_pdf_text_is_extracted() -> None:
    assert "Quarterly budget review" in extract_text("a.pdf", make_pdf("Quarterly budget review"))


def test_docx_paragraphs_and_tables_are_extracted() -> None:
    data = make_docx("First paragraph", "Second one", table=[["name", "owner"], ["alpha", "Ram"]])

    text = extract_text("a.docx", data)

    assert "First paragraph" in text and "Second one" in text
    assert "alpha | Ram" in text


@pytest.mark.parametrize("name", ["a.exe", "a", "a.docx.exe", "a.html"])
def test_unsupported_extensions_are_rejected(name: str) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        detect_type(name, b"anything")


def test_content_must_match_the_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        detect_type("fake.pdf", b"<html>not a pdf</html>")
    with pytest.raises(UnsupportedFileTypeError):
        detect_type("fake.docx", b"plain text")
    with pytest.raises(UnsupportedFileTypeError):
        detect_type("binary.txt", b"abc\x00\x01\x02")


def test_corrupt_files_fail_with_a_safe_message() -> None:
    with pytest.raises(ExtractionError) as pdf_error:
        extract_text("a.pdf", b"%PDF-1.4 garbage")
    with pytest.raises(ExtractionError) as docx_error:
        extract_text("a.docx", b"PK\x03\x04 not really a zip")

    for error in (pdf_error, docx_error):
        assert "corrupt" in str(error.value)
        assert "Traceback" not in str(error.value)


def test_empty_content_is_an_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text("a.txt", b"   \n  ")
