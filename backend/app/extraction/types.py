from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedText:
    pages: list[str]
    source: str
    layout_pages: list[str] | None = None

    @property
    def full_text(self) -> str:
        return "\n\n".join(page for page in self.pages if page).strip()
