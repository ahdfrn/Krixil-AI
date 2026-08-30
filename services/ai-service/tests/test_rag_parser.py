import io

import docx
import pytest
from pypdf import PdfWriter

from app.rag.parser import UnsupportedFileType, content_type_for, extension_of, parse_document


def test_extension_of_returns_lowercase_extension():
    assert extension_of("Report.PDF") == "pdf"


def test_extension_of_raises_without_extension():
    with pytest.raises(UnsupportedFileType):
        extension_of("noextension")


def test_content_type_for_known_extension():
    assert content_type_for("pdf") == "application/pdf"


def test_content_type_for_unknown_extension_falls_back_to_octet_stream():
    assert content_type_for("xyz") == "application/octet-stream"


def test_parse_document_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileType):
        parse_document("virus.exe", b"data")


def test_parse_txt_returns_single_page_with_none_page_number():
    pages = parse_document("notes.txt", "hello world".encode())
    assert pages == [(None, "hello world")]


def test_parse_csv_returns_single_page_with_none_page_number():
    pages = parse_document("data.csv", "a,b\n1,2".encode())
    assert pages == [(None, "a,b\n1,2")]


def test_parse_docx_extracts_paragraph_text():
    document = docx.Document()
    document.add_paragraph("Hello from docx")
    buffer = io.BytesIO()
    document.save(buffer)

    pages = parse_document("report.docx", buffer.getvalue())
    assert pages == [(None, "Hello from docx")]


def test_parse_pdf_returns_one_entry_per_page_numbered_from_one():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    pages = parse_document("doc.pdf", buffer.getvalue())
    assert [page_number for page_number, _ in pages] == [1, 2]
