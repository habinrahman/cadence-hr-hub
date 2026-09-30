"""Decide whether extracted text is a CV. The filename is not an input."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CV_PAIR = ("experience", "education")
_INVOICE_SUPPORT = ("bill to", "total due", "amount due", "invoice number", "subtotal", "balance due")
_COVER_CLOSINGS = ("sincerely", "yours faithfully", "yours sincerely")


@dataclass(frozen=True)
class Classification:
    kind: str
    reason: str | None
    signals: tuple[str, ...]


def classify_document(text: str) -> Classification:
    """Return cv, or a non-CV reason. A real CV that mentions one noisy word stays a CV."""
    if _has(text, "experience") and _has(text, "education"):
        return Classification("cv", None, _CV_PAIR)
    invoice = tuple(phrase for phrase in _INVOICE_SUPPORT if _has(text, phrase))
    if _has(text, "invoice") and len(invoice) >= 2:
        return Classification("non_cv", "non_cv_invoice", ("invoice", *invoice))
    closing = tuple(phrase for phrase in _COVER_CLOSINGS if _has(text, phrase))
    if _has(text, "i am writing") or (_has(text, "dear") and closing):
        return Classification("non_cv", "non_cv_cover_letter", ("cover_letter", *closing))
    if _has(text, "job description") and _has(text, "responsibilities") and not _has(text, "education"):
        if _early(text, "job description"):
            return Classification("non_cv", "non_cv_job_description", ("job_description", "responsibilities"))
    return Classification("cv", None, ())


def _has(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, text.casefold()) is not None


def _early(text: str, phrase: str) -> bool:
    compact = re.sub(r"\s+", " ", text.casefold())
    return phrase in compact[:600]
