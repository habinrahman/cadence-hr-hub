"""Legacy .doc files are converted with headless LibreOffice, then read as DOCX."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from app.jobs.errors import PermanentJobError


class DocConverter(Protocol):
    def convert_to_docx(self, data: bytes) -> bytes: ...


class ConverterUnavailable(PermanentJobError):
    def __init__(self) -> None:
        super().__init__("doc_converter_unavailable")


class LibreOfficeDocConverter:
    def convert_to_docx(self, data: bytes) -> bytes:
        if shutil.which("soffice") is None:
            raise ConverterUnavailable()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.doc"
            source.write_bytes(data)
            completed = subprocess.run(
                ["soffice", "--headless", "--convert-to", "docx", "--outdir", tmp, str(source)],
                check=False,
                timeout=60,
                capture_output=True,
            )
            output = Path(tmp) / "input.docx"
            if completed.returncode != 0 or not output.is_file():
                raise PermanentJobError("doc_conversion_failed")
            return output.read_bytes()
