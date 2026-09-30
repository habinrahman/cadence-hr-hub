from __future__ import annotations

import pymupdf

from app.extraction.textutil import clean_text
from app.extraction.types import ExtractedText
from app.jobs.errors import PermanentJobError


def extract_pdf(data: bytes) -> ExtractedText:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PermanentJobError("corrupt_pdf") from exc
    try:
        if document.needs_pass:
            raise PermanentJobError("encrypted_pdf")
        original: list[str] = []
        layout: list[str] = []
        reordered = False
        for page in document:
            raw = clean_text(page.get_text() or "")
            original.append(raw)
            columns = _column_text(page)
            if columns is None:
                layout.append(raw)
            else:
                reordered = True
                layout.append(clean_text(columns))
    except PermanentJobError:
        raise
    except Exception as exc:
        raise PermanentJobError("corrupt_pdf") from exc
    finally:
        document.close()
    return ExtractedText(
        pages=original,
        source="text_layer",
        layout_pages=layout if reordered else None,
    )


def _column_text(page) -> str | None:
    """Read left column then right column when a clear vertical gap splits the page."""
    items: list[tuple[float, float, str]] = []
    for block in page.get_text("blocks") or []:
        if len(block) < 5:
            continue
        x0, y0, _x1, _y1, content = block[:5]
        text = str(content).strip()
        if not text:
            continue
        items.append((float(x0), float(y0), text))
    if len(items) < 2:
        return None
    xs = sorted(item[0] for item in items)
    gap_at = max(range(len(xs) - 1), key=lambda index: xs[index + 1] - xs[index])
    gap = xs[gap_at + 1] - xs[gap_at]
    split = (xs[gap_at] + xs[gap_at + 1]) / 2
    width = float(page.rect.width)
    if gap < 36 or not (width * 0.25 < split < width * 0.75):
        return None
    left = [item for item in items if item[0] < split]
    right = [item for item in items if item[0] >= split]
    left_text = "\n".join(text for _x, _y, text in sorted(left, key=lambda item: (item[1], item[0])))
    right_text = "\n".join(text for _x, _y, text in sorted(right, key=lambda item: (item[1], item[0])))
    if len(left_text) < 40 or len(right_text) < 40:
        return None
    return f"{left_text}\n{right_text}"
