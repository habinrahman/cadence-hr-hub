from __future__ import annotations

import hashlib
import re


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def alnum_count(value: str) -> int:
    return sum(character.isalnum() for character in value)


def clean_text(value: str) -> str:
    value = value.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def chunk_text(value: str, size: int) -> list[str]:
    if not value:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if buffer and len(candidate) > size:
            chunks.append(buffer)
            buffer = paragraph
        else:
            buffer = candidate
        while len(buffer) > size:
            chunks.append(buffer[:size])
            buffer = buffer[size:].strip()
    if buffer:
        chunks.append(buffer)
    return chunks


def page_for_snippet(pages: list[str], snippet: str) -> int | None:
    needle = normalize_ws(snippet)[:80]
    if not needle:
        return None
    for index, page in enumerate(pages, start=1):
        if needle in normalize_ws(page):
            return index
    return None
