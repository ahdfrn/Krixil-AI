import re


def clean_text(text: str) -> str:
    # Collapse runs of whitespace (extra spaces, repeated blank lines from PDF extraction) into
    # single spaces/newlines — cheap normalization, not a full text-cleaning pipeline.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-based sliding window with overlap. Simple and dependency-free; a token-aware
    chunker (tiktoken or similar) would size chunks more precisely against a model's context
    budget — worth adding if chunk-size-related quality issues actually show up."""
    text = clean_text(text)
    if not text:
        return []

    step = chunk_size - overlap
    if step <= 0:
        raise ValueError(
            f"chunk_overlap ({overlap}) must be smaller than chunk_size ({chunk_size})"
        )
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks
