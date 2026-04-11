from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    chunk_index: int
    text: str


_SPLIT_PATTERN = re.compile(r"(?<=[。.!?])|\n\n+|\n|\s+")


def split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    current = ""

    for part in _split_keep_separators(normalized):
        if len(part) > chunk_size:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split(part, chunk_size, chunk_overlap))
            current = ""
            continue

        if len(current) + len(part) > chunk_size:
            if current.strip():
                chunks.append(current.strip())
                current = _tail(current, chunk_overlap)
            if len(current) + len(part) > chunk_size:
                current = ""

        current += part

    if current.strip():
        chunk = current.strip()
        if not chunks or chunk != chunks[-1]:
            chunks.append(chunk)

    return [chunk for chunk in chunks if chunk]


def chunk_pages(
    pages: list[TextPage],
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    chunk_index = 0
    for page in pages:
        for text in split_text(page.text, chunk_size, chunk_overlap):
            chunks.append(
                TextChunk(
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    text=text,
                )
            )
            chunk_index += 1
    return chunks


def _split_keep_separators(text: str) -> list[str]:
    parts = _SPLIT_PATTERN.split(text)
    separators = _SPLIT_PATTERN.findall(text)
    merged: list[str] = []
    for index, part in enumerate(parts):
        if part:
            merged.append(part)
        if index < len(separators) and separators[index]:
            merged.append(separators[index])
    return merged


def _tail(text: str, length: int) -> str:
    if length <= 0:
        return ""
    stripped = text.strip()
    return stripped[-length:] if len(stripped) > length else stripped


def _hard_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    step = chunk_size - chunk_overlap if chunk_overlap else chunk_size
    chunks = []
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks
