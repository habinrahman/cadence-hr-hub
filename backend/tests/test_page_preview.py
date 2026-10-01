"""Page previews for the comparison workspace: images only, recruiter only, tied to a review, audited without text."""

import struct
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import AuditEvent
from app.services.ingest import ingest_bytes
from tests.test_foundation import ENGINEER, RECRUITER, _actor, make_pdf
from tests.test_review_compare import NEW, OLD, _pair

PNG = b"\x89PNG\r\n\x1a\n"
FOCUS = "Google, Senior Engineer"


def _preview(review_id, document_id, page=1, headers=RECRUITER, **params):
    with TestClient(app) as client:
        return client.get(f"/reviews/{review_id}/documents/{document_id}/pages/{page}/preview", headers=headers, params=params)


def _width(png: bytes) -> int:
    return struct.unpack(">I", png[16:20])[0]


def test_recruiter_gets_an_image_of_either_cv_and_nothing_else(session):
    review, old, new = _pair(session, OLD, NEW)
    for document in (old, new):
        response = _preview(review.id, document.id)
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(PNG)
        assert response.headers["x-preview-pages"] == "1"
        assert response.headers["cache-control"] == "no-store"
        assert b"%PDF" not in response.content


def test_access_rules(session):
    review, old, _new = _pair(session, OLD, NEW)
    with TestClient(app) as client:
        path = f"/reviews/{review.id}/documents/{old.id}/pages/1/preview"
        assert client.get(path).status_code == 401
        denied = client.get(path, headers=ENGINEER)
        malformed = client.get(f"/reviews/{review.id}/documents/not-a-uuid/pages/1/preview", headers=RECRUITER)
    assert denied.status_code == 403
    assert not denied.content.startswith(PNG)
    assert malformed.status_code == 422


def test_only_the_two_documents_of_the_review_can_be_previewed(session):
    review, _old, _new = _pair(session, OLD, NEW)
    stranger = ingest_bytes(
        session,
        filename="someone-else.pdf",
        data=make_pdf("Someone Else\nelse@example.com\nExperience\nOther Corp, Analyst\n"),
        actor=_actor(session),
    ).document
    session.commit()
    assert _preview(review.id, stranger.id).status_code == 404
    assert _preview(review.id, "00000000-0000-4000-8000-000000000000").status_code == 404
    assert _preview("00000000-0000-4000-8000-000000000000", stranger.id).status_code == 404


def test_pages_outside_the_document_are_not_found(session):
    review, _old, new = _pair(session, OLD, NEW)
    assert _preview(review.id, new.id, page=0).status_code == 404
    assert _preview(review.id, new.id, page=2).status_code == 404
    assert _preview(review.id, new.id, page=-1).status_code == 404


def test_a_word_document_has_no_visual_preview(session):
    review, _old, new = _pair(session, OLD, NEW)
    new.media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    session.commit()
    response = _preview(review.id, new.id)
    assert response.status_code == 415
    assert response.json()["detail"] == "preview_unavailable"


def test_a_file_that_cannot_be_drawn_is_reported_not_crashed(session):
    review, _old, new = _pair(session, OLD, NEW)
    Path(get_settings().storage_dir, new.storage_key).write_bytes(b"this is not a pdf")
    response = _preview(review.id, new.id)
    assert response.status_code == 422
    assert response.json()["detail"] == "preview_failed"


def test_a_missing_stored_file_is_not_found(session):
    review, _old, new = _pair(session, OLD, NEW)
    Path(get_settings().storage_dir, new.storage_key).unlink()
    assert _preview(review.id, new.id).status_code == 404


def test_lines_only_in_this_cv_are_marked_and_identical_cvs_have_no_marks(session):
    review, old, new = _pair(session, OLD, NEW)
    new_marks = int(_preview(review.id, new.id).headers["x-preview-highlights"])
    old_marks = int(_preview(review.id, old.id).headers["x-preview-highlights"])
    assert new_marks > 0
    assert old_marks >= 0
    assert new_marks > old_marks


def test_identical_text_marks_nothing(session):
    review, old, new = _pair(session, OLD, OLD)
    assert int(_preview(review.id, new.id).headers["x-preview-highlights"]) == 0
    assert int(_preview(review.id, old.id).headers["x-preview-highlights"]) == 0


def test_the_selected_evidence_quote_is_outlined_on_the_page(session):
    review, _old, new = _pair(session, OLD, NEW)
    plain = _preview(review.id, new.id).content
    outlined = _preview(review.id, new.id, focus=FOCUS).content
    assert outlined.startswith(PNG) and outlined != plain
    assert _preview(review.id, new.id, focus="text that is nowhere on this page").content == plain


def test_width_is_clamped_and_long_quotes_are_refused(session):
    review, _old, new = _pair(session, OLD, NEW)
    assert _width(_preview(review.id, new.id, width=100).content) == 600
    assert _width(_preview(review.id, new.id, width=99999).content) == 1400
    assert _width(_preview(review.id, new.id).content) == 900
    assert _preview(review.id, new.id, focus="x" * 301).status_code == 422


def test_each_render_is_audited_with_ids_only(session):
    review, old, new = _pair(session, OLD, NEW)
    assert _preview(review.id, old.id).status_code == 200
    assert _preview(review.id, new.id, focus=FOCUS).status_code == 200
    assert _preview(review.id, new.id, page=9).status_code == 404
    session.expire_all()
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "cv_preview_viewed")).all()
    assert len(events) == 2
    assert {event.entity_id for event in events} == {old.id, new.id}
    for event in events:
        assert event.actor_kind == "user"
        assert event.entity_type == "candidate_document"
        assert set(event.detail) == {"review_id", "document_id"}
    everything = " ".join(f"{e.action} {e.detail}" for e in session.scalars(select(AuditEvent)).all())
    assert "Google" not in everything and "Senior Engineer" not in everything and "@" not in everything


def test_a_refused_request_writes_no_audit_row(session):
    review, old, _new = _pair(session, OLD, NEW)
    _preview(review.id, old.id, headers=ENGINEER)
    _preview(review.id, old.id, page=5)
    session.expire_all()
    assert session.scalars(select(AuditEvent).where(AuditEvent.action == "cv_preview_viewed")).all() == []
