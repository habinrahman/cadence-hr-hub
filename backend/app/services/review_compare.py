"""Read-only comparison of an incoming CV with a candidate's existing CV.

Nothing here decides a review or writes a row. It reads the stored pages of two documents, runs the same
deterministic section parser and quote check the pipeline uses, and reports what it can prove.

Rules that keep it honest:
- A section that the parser found nothing in is "not extracted". That is not the same as "removed".
- Items are only labelled added, changed or not found when BOTH documents produced items for that section.
- Every item carries the quote and page it was read from. An item whose quote is not in the page text is dropped.
- A filename is never an input. Dates come from the text, and the upload date is shown separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.cvdates import dates_in_text, explicit_dates
from app.domain.identity import name_similarity
from app.extraction.deterministic import DeterministicExtractor, assign_pages
from app.extraction.draft import ExtractionDraft, quote_in_source
from app.extraction.textutil import alnum_count, normalize_ws
from app.models import Candidate, CandidateDocument, DocumentPage, DuplicateReview

DECIDED = {"accepted_update", "recorded_duplicate", "created_separate"}
_TEXT_DIFF_LIMIT = 80
_LINE_LIMIT = 300

_NOT_EXTRACTED_NOTE = (
    "Nothing was extracted from the {side} CV for this section, so it cannot be compared. "
    "That does not mean the information is absent."
)
_UNAVAILABLE_NOTE = "The {side} CV has no readable text on file, so this cannot be compared."
_TEXT_NOTE = (
    "Lines are compared after collapsing spaces. A line shown as only in one CV may simply be worded or "
    "wrapped differently, so read it together with the source pages."
)


# The pipeline's phone finder also matches date-shaped digit runs such as 2023-01-01. Those are dates, and telling a
# recruiter that a "new phone number" appeared because a job started on one would be a false claim.
_DATE_SHAPED = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


class CompareError(Exception):
    def __init__(self, code: str, status: int = 404) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass
class Item:
    key: str
    signature: str
    label: str
    quote: str
    page: int | None


@dataclass
class Side:
    document: CandidateDocument | None
    pages: list[tuple[int, str, str]] = field(default_factory=list)  # number, original, normalized
    draft: ExtractionDraft | None = None

    @property
    def state(self) -> str:
        if self.document is None:
            return "no_document"
        if self.document.status == "needs_ocr":
            return "needs_ocr"
        if self.document.status in {"failed", "quarantined"}:
            return self.document.status
        if not self.pages:
            return "no_text"
        return "ok"

    @property
    def originals(self) -> list[str]:
        return [original for _number, original, _normalized in self.pages]


def build_comparison(session: Session, review: DuplicateReview, *, candidate_id: UUID | None) -> dict:
    base = {
        "review_id": str(review.id),
        "status": review.status,
        "decided_at": review.decided_at.isoformat() if review.decided_at else None,
    }
    if review.document_id is None:
        return {**base, "available": False, "reason": "excel_row", "warnings": [], "candidates": [],
                "candidate": None, "existing": None, "incoming": None, "fields": [], "dates": None,
                "text_diff": None, "identical_bytes": False}

    incoming_doc = session.get(CandidateDocument, review.document_id)
    if incoming_doc is None:
        return {**base, "available": False, "reason": "incoming_document_missing", "warnings": [],
                "candidates": [], "candidate": None, "existing": None, "incoming": None, "fields": [],
                "dates": None, "text_diff": None, "identical_bytes": False}

    allowed = [UUID(item) for item in review.signals.get("candidate_ids", [])]
    if candidate_id is not None and allowed and candidate_id not in allowed:
        raise CompareError("not_found")
    chosen = candidate_id or review.candidate_id or (allowed[0] if allowed else None)
    candidates = [_candidate_payload(session, item) for item in allowed or ([chosen] if chosen else [])]
    candidate = session.get(Candidate, chosen) if chosen else None

    warnings: list[str] = []
    if review.status in DECIDED:
        warnings.append("review_decided")
    if review.signals.get("ambiguous") and len(candidates) > 1:
        warnings.append("multiple_candidates")
    if candidate is not None and candidate.merged_into_id is not None:
        warnings.append("candidate_merged")

    existing_doc = _existing_document(session, incoming_doc, chosen, warnings)
    incoming = _load_side(session, incoming_doc)
    existing = _load_side(session, existing_doc)

    identical = bool(existing_doc and existing_doc.sha256 == incoming_doc.sha256)
    if identical:
        warnings.append("identical_bytes")

    dates = _dates(existing, incoming)
    if dates and dates["conflict"]:
        warnings.append("date_conflict")

    payload = {
        **base,
        "available": candidate is not None and existing_doc is not None,
        "reason": None if candidate is not None and existing_doc is not None
        else ("no_candidate" if candidate is None else "no_existing_document"),
        "warnings": warnings,
        "candidates": candidates,
        "candidate": _candidate_payload(session, chosen) if candidate is not None else None,
        "existing": _side_payload(existing),
        "incoming": _side_payload(incoming),
        "identical_bytes": identical,
        "fields": _fields(existing, incoming, candidate),
        "dates": dates,
        "text_diff": _text_diff(existing, incoming),
    }
    return payload


def _candidate_payload(session: Session, candidate_id: UUID | None) -> dict | None:
    if candidate_id is None:
        return None
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        return {"id": str(candidate_id), "name": None, "merged_into_id": None}
    return {
        "id": str(candidate.id),
        "name": candidate.display_name,
        "merged_into_id": str(candidate.merged_into_id) if candidate.merged_into_id else None,
    }


def _existing_document(session: Session, incoming: CandidateDocument, candidate_id: UUID | None, warnings: list[str]):
    """The CV the incoming one is compared with.

    After an accepted update the incoming CV is current and points at the one it replaced, so a decided review
    still shows the same two documents. Otherwise it is the candidate's current CV.
    """
    if incoming.supersedes_document_id is not None:
        prior = session.get(CandidateDocument, incoming.supersedes_document_id)
        if prior is not None:
            return prior
    if candidate_id is None:
        return None
    current = session.scalar(
        select(CandidateDocument).where(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.is_current.is_(True),
            CandidateDocument.id != incoming.id,
        )
    )
    if current is not None:
        return current
    latest = session.scalar(
        select(CandidateDocument)
        .where(CandidateDocument.candidate_id == candidate_id, CandidateDocument.id != incoming.id)
        .order_by(CandidateDocument.received_at.desc())
    )
    if latest is not None:
        warnings.append("no_current_document")
    return latest


def _load_side(session: Session, document: CandidateDocument | None) -> Side:
    if document is None:
        return Side(document=None)
    rows = session.execute(
        select(DocumentPage.page_number, DocumentPage.original_text, DocumentPage.normalized_text)
        .where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).all()
    side = Side(document=document, pages=[(number, original, normalized) for number, original, normalized in rows])
    if side.state == "ok":
        try:
            draft = DeterministicExtractor().extract(
                document_id=document.id,
                source_text="\n\n".join(normalized for _n, _o, normalized in side.pages),
                prompt_version="compare-v1",
            )
            assign_pages(draft, side.originals)
            side.draft = draft
        except ValidationError:
            side.draft = None
    return side


def _side_payload(side: Side) -> dict:
    document = side.document
    if document is None:
        return {"state": "no_document", "document": None}
    return {
        "state": side.state,
        "document": {
            "id": str(document.id),
            "filename": document.original_filename,
            "media_type": document.media_type,
            "byte_size": document.byte_size,
            "received_at": document.received_at.isoformat(),
            "page_count": document.page_count if document.page_count is not None else len(side.pages),
            "status": document.status,
            "is_current": document.is_current,
            "text_source": document.text_source,
            "language_code": document.language_code,
            "error_code": document.error_code,
        },
    }


# ---------- structured fields ----------


def _verified(side: Side, quote: str | None, page: int | None) -> bool:
    return bool(quote) and quote_in_source(side.originals, quote, page)


def _experience(side: Side) -> list[Item]:
    if side.draft is None:
        return []
    items: list[Item] = []
    for row in side.draft.experiences:
        if not _verified(side, row.employer_quote, row.page):
            continue
        title = row.title or ""
        span = f"{row.start_date} to {row.end_date or 'present'}" if row.start_date else ""
        label = " — ".join(part for part in (row.employer, title, span) if part)
        items.append(Item(row.employer.casefold(), f"{title.casefold()}|{row.start_date}|{row.end_date}", label,
                          row.employer_quote, row.page))
    return items


def _education(side: Side) -> list[Item]:
    if side.draft is None:
        return []
    items: list[Item] = []
    for row in side.draft.education:
        if not _verified(side, row.institution_quote, row.page):
            continue
        credential = row.credential or ""
        label = " — ".join(part for part in (row.institution, credential) if part)
        items.append(Item(row.institution.casefold(), credential.casefold(), label, row.institution_quote, row.page))
    return items


def _skills(side: Side) -> list[Item]:
    if side.draft is None:
        return []
    return [
        Item(row.name.casefold(), "", row.name, row.quote, row.page)
        for row in side.draft.skills
        if _verified(side, row.quote, row.page)
    ]


def _certificates(side: Side) -> list[Item]:
    if side.draft is None:
        return []
    return [
        Item(row.name.casefold(), row.kind, f"{row.name} ({row.kind})", row.quote, row.page)
        for row in side.draft.certificates
        if _verified(side, row.quote, row.page)
    ]


def _contacts(side: Side, kind: str) -> list[Item]:
    if side.draft is None:
        return []
    items: list[Item] = []
    for row in side.draft.contacts:
        if row.kind != kind or not _verified(side, row.quote, row.page):
            continue
        if kind == "phone" and _DATE_SHAPED.fullmatch(row.quote.strip()):
            continue
        page = row.page or _page_of(side, row.quote)
        # Show the contact as the CV writes it. The normalised value is only the comparison key. A phone is keyed on its
        # last 8 digits, so 052 444 9121 and +972 52 444 9121 are the same number, as in domain.identity.phones_match.
        key = row.value.casefold()
        if kind == "phone" and len(key) >= 8:
            key = key[-8:]
        items.append(Item(key, "", row.quote.strip(), row.quote, page))
    return items


def _page_of(side: Side, quote: str) -> int | None:
    needle = normalize_ws(quote)
    for number, original, _normalized in side.pages:
        if needle and needle in normalize_ws(original):
            return number
    return None


def _evidence(item: Item | None) -> dict | None:
    if item is None:
        return None
    return {"label": item.label, "evidence": {"quote": item.quote[:1000], "page": item.page}}


def _side_state(side: Side, items: list[Item]) -> str:
    if side.state != "ok":
        return "unavailable"
    return "extracted" if items else "not_extracted"


def _field(key: str, label: str, existing: Side, incoming: Side, left: list[Item], right: list[Item]) -> dict:
    existing_state = _side_state(existing, left)
    incoming_state = _side_state(incoming, right)
    comparable = existing_state == "extracted" and incoming_state == "extracted"
    note = None
    if not comparable:
        for name, state, side in (("previous", existing_state, existing), ("new", incoming_state, incoming)):
            if state == "unavailable":
                note = _UNAVAILABLE_NOTE.format(side=name)
                break
            if state == "not_extracted":
                note = _NOT_EXTRACTED_NOTE.format(side=name)
                break
        rows = [{"status": "unknown", "label": item.label, "existing": _evidence(item), "incoming": None} for item in left]
        rows += [{"status": "unknown", "label": item.label, "existing": None, "incoming": _evidence(item)} for item in right]
    else:
        rows = _diff(left, right)
    return {
        "key": key,
        "label": label,
        "comparable": comparable,
        "existing_state": existing_state,
        "incoming_state": incoming_state,
        "note": note,
        "items": rows,
    }


def _diff(existing: list[Item], incoming: list[Item]) -> list[dict]:
    """Label items only because both documents produced items for this section."""
    unused = list(range(len(existing)))
    rows: list[dict] = []

    def take(predicate) -> int | None:
        for position in unused:
            if predicate(existing[position]):
                unused.remove(position)
                return position
        return None

    for item in incoming:
        same = take(lambda other: other.key == item.key and other.signature == item.signature)
        if same is not None:
            rows.append({"status": "same", "label": item.label, "existing": _evidence(existing[same]),
                         "incoming": _evidence(item)})
            continue
        changed = take(lambda other: other.key == item.key)
        if changed is not None:
            rows.append({"status": "changed", "label": item.label, "existing": _evidence(existing[changed]),
                         "incoming": _evidence(item)})
            continue
        rows.append({"status": "added", "label": item.label, "existing": None, "incoming": _evidence(item)})
    for position in unused:
        rows.append({"status": "only_existing", "label": existing[position].label,
                     "existing": _evidence(existing[position]), "incoming": None})
    order = {"changed": 0, "added": 1, "only_existing": 2, "same": 3}
    rows.sort(key=lambda row: order[row["status"]])
    return rows


def _name(side: Side) -> list[Item]:
    draft = side.draft
    if draft is None or not draft.display_name or not draft.display_name_quote:
        return []
    if not quote_in_source(side.originals, draft.display_name_quote, None):
        return []
    return [Item("name", "", draft.display_name, draft.display_name_quote, _page_of(side, draft.display_name_quote))]


def _name_field(existing: Side, incoming: Side, candidate: Candidate | None) -> dict:
    left, right = _name(existing), _name(incoming)
    field_row = _field("name", "Name", existing, incoming, left, right)
    if field_row["comparable"]:
        a, b = left[0], right[0]
        same = normalize_ws(a.label).casefold() == normalize_ws(b.label).casefold()
        similarity = name_similarity(a.label, b.label)
        field_row["items"] = [{
            "status": "same" if same else "changed",
            "label": b.label,
            "existing": _evidence(a),
            "incoming": _evidence(b),
            "similarity": None if similarity is None else round(similarity, 2),
        }]
    field_row["stored_name"] = candidate.display_name if candidate is not None else None
    return field_row


def _fields(existing: Side, incoming: Side, candidate: Candidate | None) -> list[dict]:
    return [
        _name_field(existing, incoming, candidate),
        _field("email", "Email", existing, incoming, _contacts(existing, "email"), _contacts(incoming, "email")),
        _field("phone", "Phone", existing, incoming, _contacts(existing, "phone"), _contacts(incoming, "phone")),
        _field("experience", "Experience", existing, incoming, _experience(existing), _experience(incoming)),
        _field("education", "Education", existing, incoming, _education(existing), _education(incoming)),
        _field("skills", "Skills", existing, incoming, _skills(existing), _skills(incoming)),
        _field("certificates", "Certificates and qualifications", existing, incoming,
               _certificates(existing), _certificates(incoming)),
    ]


# ---------- dates ----------


def _date_facts(side: Side) -> dict | None:
    if side.state != "ok":
        return None
    latest: tuple[date, int] | None = None
    labelled: tuple[date, int] | None = None
    for number, original, _normalized in side.pages:
        for found in dates_in_text(original):
            if latest is None or found > latest[0]:
                latest = (found, number)
        for found in explicit_dates(original):
            if labelled is None or found > labelled[0]:
                labelled = (found, number)
    return {
        "latest_mentioned": None if latest is None else {"date": latest[0].isoformat(), "page": latest[1]},
        "labelled_version": None if labelled is None else {"date": labelled[0].isoformat(), "page": labelled[1]},
    }


def _newer(existing: dict | None, incoming: dict | None) -> str | None:
    if not existing or not incoming:
        return None
    left, right = date.fromisoformat(existing["date"]), date.fromisoformat(incoming["date"])
    if right > left:
        return "incoming"
    if left > right:
        return "existing"
    return "same"


def _dates(existing: Side, incoming: Side) -> dict:
    left, right = _date_facts(existing), _date_facts(incoming)
    by_mentioned = _newer((left or {}).get("latest_mentioned"), (right or {}).get("latest_mentioned"))
    by_labelled = _newer((left or {}).get("labelled_version"), (right or {}).get("labelled_version"))
    decisive = {"incoming", "existing"}
    conflict = by_mentioned in decisive and by_labelled in decisive and by_mentioned != by_labelled
    return {
        "existing": left,
        "incoming": right,
        "uploaded": {
            "existing": existing.document.received_at.isoformat() if existing.document else None,
            "incoming": incoming.document.received_at.isoformat() if incoming.document else None,
        },
        "newer_by_mentioned": by_mentioned,
        "newer_by_labelled": by_labelled,
        "conflict": conflict,
    }


# ---------- raw text ----------


def _lines(side: Side) -> dict[str, tuple[int, str]]:
    found: dict[str, tuple[int, str]] = {}
    for number, original, _normalized in side.pages:
        for raw in original.splitlines():
            line = normalize_ws(raw)
            if alnum_count(line) < 3:
                continue
            found.setdefault(line.casefold(), (number, line))
    return found


def _text_diff(existing: Side, incoming: Side) -> dict:
    if existing.state != "ok" or incoming.state != "ok":
        return {"available": False, "note": _TEXT_NOTE, "incoming_only": [], "existing_only": [],
                "incoming_only_count": 0, "existing_only_count": 0, "truncated": False}
    left, right = _lines(existing), _lines(incoming)
    incoming_only = [(page, text) for key, (page, text) in right.items() if key not in left]
    existing_only = [(page, text) for key, (page, text) in left.items() if key not in right]

    def rows(items: list[tuple[int, str]]) -> list[dict]:
        return [{"page": page, "text": text[:_LINE_LIMIT]} for page, text in items[:_TEXT_DIFF_LIMIT]]

    return {
        "available": True,
        "note": _TEXT_NOTE,
        "incoming_only": rows(incoming_only),
        "existing_only": rows(existing_only),
        "incoming_only_count": len(incoming_only),
        "existing_only_count": len(existing_only),
        "truncated": len(incoming_only) > _TEXT_DIFF_LIMIT or len(existing_only) > _TEXT_DIFF_LIMIT,
    }


# ---------- page preview support ----------
# Used only by the page-preview route. They reuse the rules above and change nothing in build_comparison.


def review_documents(
    session: Session, review: DuplicateReview, candidate_id: UUID | None
) -> tuple[CandidateDocument | None, CandidateDocument | None]:
    """(existing, incoming): the two documents the comparison shows for this review, chosen by the same rules."""
    if review.document_id is None:
        return None, None
    incoming_doc = session.get(CandidateDocument, review.document_id)
    if incoming_doc is None:
        return None, None
    allowed = [UUID(item) for item in review.signals.get("candidate_ids", [])]
    if candidate_id is not None and allowed and candidate_id not in allowed:
        raise CompareError("not_found")
    chosen = candidate_id or review.candidate_id or (allowed[0] if allowed else None)
    return _existing_document(session, incoming_doc, chosen, []), incoming_doc


def _pages_only(session: Session, document: CandidateDocument | None) -> Side:
    if document is None:
        return Side(document=None)
    rows = session.execute(
        select(DocumentPage.page_number, DocumentPage.original_text, DocumentPage.normalized_text)
        .where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).all()
    return Side(document=document, pages=[(number, original, normalized) for number, original, normalized in rows])


def only_here_lines(
    session: Session,
    pair: tuple[CandidateDocument | None, CandidateDocument | None],
    which: str,
    page: int,
) -> list[str]:
    """Lines on `page` of one CV that the other CV does not contain, by the same rule as the text diff."""
    existing, incoming = _pages_only(session, pair[0]), _pages_only(session, pair[1])
    if existing.state != "ok" or incoming.state != "ok":
        return []
    left, right = _lines(existing), _lines(incoming)
    mine, other = (left, right) if which == "existing" else (right, left)
    return [text for key, (number, text) in mine.items() if key not in other and number == page]
