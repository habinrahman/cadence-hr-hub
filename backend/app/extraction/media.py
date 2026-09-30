"""Recognise files from bytes. The filename is not trusted."""

from __future__ import annotations

import zipfile
from io import BytesIO

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC = "application/msword"
JPEG = "image/jpeg"
PNG = "image/png"


class UnsupportedFile(Exception):
    code = "unsupported_file"


def detect_media_type(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return PDF
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return DOC
    if data.startswith(b"PK") and _is_docx(data):
        return DOCX
    raise UnsupportedFile


def _is_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def safe_filename(name: str | None) -> str:
    base = (name or "upload").replace("\\", "/").split("/")[-1].strip()
    base = base.replace("\x00", "") or "upload"
    return base[:500]
