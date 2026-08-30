import io

import docx
from pypdf import PdfReader

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "csv"}

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
}


class UnsupportedFileType(ValueError):
    pass


def extension_of(filename: str) -> str:
    if "." not in filename:
        raise UnsupportedFileType(f"'{filename}' has no file extension")
    return filename.rsplit(".", 1)[-1].lower()


def content_type_for(extension: str) -> str:
    return _CONTENT_TYPES.get(extension, "application/octet-stream")


def parse_document(filename: str, content: bytes) -> list[tuple[int | None, str]]:
    """Returns a list of (page_number, text) — page_number is None for formats without a
    meaningful concept of pages (docx, txt, csv), 1-indexed for PDF."""
    extension = extension_of(filename)

    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFileType(f"Unsupported file type '.{extension}' — allowed: {allowed}")

    if extension == "pdf":
        return _parse_pdf(content)
    if extension == "docx":
        return [(None, _parse_docx(content))]
    # txt and csv are already plain text — read as-is rather than reformatting csv rows, which
    # would add complexity (dialect sniffing, encoding quirks) for little retrieval benefit.
    return [(None, content.decode("utf-8", errors="replace"))]


def _parse_pdf(content: bytes) -> list[tuple[int | None, str]]:
    reader = PdfReader(io.BytesIO(content))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _parse_docx(content: bytes) -> str:
    document = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs)
