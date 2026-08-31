import pytest

from app.rag.chunker import chunk_text, clean_text


def test_clean_text_collapses_whitespace():
    assert clean_text("hello    world\n\n\n\nfoo") == "hello world\n\nfoo"


def test_clean_text_strips_null_bytes():
    # Some PDFs (unusual font/CID encodings) make pypdf's extract_text() emit literal NUL bytes,
    # which Postgres's text columns reject outright (CharacterNotInRepertoireError) — caught live
    # from a real user-uploaded PDF, not a hypothetical case.
    assert clean_text("hello\x00 world") == "hello world"


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("   ", chunk_size=100, overlap=10) == []


def test_chunk_text_short_text_returns_single_chunk():
    assert chunk_text("hello world", chunk_size=100, overlap=10) == ["hello world"]


def test_chunk_text_splits_long_text_with_overlap():
    text = "a" * 25
    chunks = chunk_text(text, chunk_size=10, overlap=3)

    assert chunks == ["aaaaaaaaaa", "aaaaaaaaaa", "aaaaaaaaaa", "aaaa"]


def test_chunk_text_raises_when_overlap_not_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=10, overlap=10)
