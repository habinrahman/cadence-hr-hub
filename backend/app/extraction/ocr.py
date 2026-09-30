"""OCR is an adapter. The pipeline calls it only when a file has no text layer."""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Protocol

import pymupdf
from PIL import Image

from app.extraction.media import JPEG, PDF, PNG

_WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


class OcrUnavailable(Exception):
    code = "ocr_unavailable"


class OcrAdapter(Protocol):
    def extract_pages(self, data: bytes, media_type: str) -> list[str]: ...


def tesseract_path() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    if _WINDOWS_TESSERACT.exists():
        return str(_WINDOWS_TESSERACT)
    return None


class TesseractOcrAdapter:
    def extract_pages(self, data: bytes, media_type: str) -> list[str]:
        binary = tesseract_path()
        if binary is None:
            raise OcrUnavailable()
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = binary
        Image.MAX_IMAGE_PIXELS = 20_000_000
        if media_type == PDF:
            return _pdf_pages(data, pytesseract)
        if media_type in {JPEG, PNG}:
            with Image.open(io.BytesIO(data)) as image:
                return [pytesseract.image_to_string(image)]
        raise OcrUnavailable()

    def extract_text(self, data: bytes, media_type: str) -> str:
        return "\n\n".join(self.extract_pages(data, media_type))


def _pdf_pages(data: bytes, pytesseract) -> list[str]:
    document = pymupdf.open(stream=data, filetype="pdf")
    pages: list[str] = []
    try:
        for page in document:
            pixmap = page.get_pixmap(dpi=200)
            with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                pages.append(pytesseract.image_to_string(image))
    finally:
        document.close()
    return pages
