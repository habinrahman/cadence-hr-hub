"""Render one page of a stored PDF as a PNG, with the lines that differ marked on the page itself.

Only images leave the server. The original file is never returned.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

AMBER = (0.96, 0.62, 0.04)
BLUE = (0.12, 0.37, 0.84)
MIN_WIDTH, MAX_WIDTH = 600, 1400
_SEARCH_FULL = 200
_SEARCH_SHORT = 60


class PreviewError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class PreviewResult:
    png: bytes
    page_count: int
    highlights: int


def clamp_width(width: int) -> int:
    return max(MIN_WIDTH, min(MAX_WIDTH, width))


def _find(page: pymupdf.Page, text: str) -> list[pymupdf.Rect]:
    """Best effort. A line wrapped across text runs may not match in full, so fall back to its start."""
    needle = " ".join(text.split())
    if not needle:
        return []
    for candidate in (needle[:_SEARCH_FULL], needle[:_SEARCH_SHORT]):
        hits = page.search_for(candidate)
        if hits:
            return hits
    return []


def render_page(data: bytes, number: int, *, width: int, mark: list[str], focus: str | None) -> PreviewResult:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise PreviewError("preview_failed") from None
    try:
        if document.needs_pass or document.is_encrypted:
            raise PreviewError("preview_failed")
        count = document.page_count
        if number < 1 or number > count:
            raise PreviewError("page_out_of_range")
        try:
            page = document[number - 1]
            highlights = 0
            for line in mark:
                for rect in _find(page, line):
                    page.draw_rect(rect, color=None, fill=AMBER, fill_opacity=0.35)
                    highlights += 1
            if focus:
                for rect in _find(page, focus)[:3]:
                    page.draw_rect(rect + (-2, -2, 2, 2), color=BLUE, width=1.6)
            zoom = clamp_width(width) / page.rect.width
            png = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")
        except PreviewError:
            raise
        except Exception:
            raise PreviewError("preview_failed") from None
        return PreviewResult(png=png, page_count=count, highlights=highlights)
    finally:
        document.close()
