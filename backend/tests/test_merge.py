"""Two existing profiles join only when a recruiter confirms."""

from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import provision
from app.domain.actor import SYSTEM, Actor
from app.main import app
from app.models import (
    Application,
    AuditEvent,
    Candidate,
    CandidateContact,
    CandidateDocument,
    CandidateExperience,
    User,
)
from app.services.merge import MergeError, merge_profiles
from tests.test_mail import ENGINEER, RECRUITER


def _candidate(name: str, when: datetime) -> Candidate:
    return Candidate(source="upload", display_name=name, created_at=when)


def _document(candidate: Candidate, stamp: str, received: datetime, *, current: bool) -> CandidateDocument:
    return CandidateDocument(
        candidate_id=candidate.id,
        sha256=f"{stamp}".ljust(64, "b"),
        original_filename=f"{stamp}.pdf",
        media_type="application/pdf",
        byte_size=20,
        storage_key=f"merge/{stamp}",
        status="profiled",
        is_current=current,
        processing_version=1,
        received_at=received,
    )


def _pair(session):
    older = _candidate("Ada Lovelace", datetime(2020, 1, 1, tzinfo=UTC))
    newer = _candidate("A. Lovelace", datetime(2024, 6, 1, tzinfo=UTC))
    session.add_all([older, newer])
    session.flush()
    first = _document(older, "older", datetime(2020, 2, 1, tzinfo=UTC), current=True)
    second = _document(newer, "newer", datetime(2024, 7, 1, tzinfo=UTC), current=True)
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            Application(candidate_id=older.id, source="upload", received_at=datetime(2020, 2, 1, tzinfo=UTC)),
            Application(candidate_id=newer.id, source="upload", received_at=datetime(2024, 7, 1, tzinfo=UTC)),
            CandidateContact(
                candidate_id=older.id,
                kind="email",
                value_raw="ada@example.com",
                value_normalized="ada@example.com",
                is_primary=True,
            ),
            CandidateContact(
                candidate_id=newer.id,
                kind="phone",
                value_raw="97336001111",
                value_normalized="97336001111",
                is_primary=True,
            ),
            CandidateExperience(
                candidate_id=older.id,
                source_document_id=first.id,
                employer="Analytical Engines",
                title="Engineer",
            ),
            CandidateExperience(
                candidate_id=newer.id,
                source_document_id=second.id,
                employer="Harbour Lab",
                title="Analyst",
            ),
        ]
    )
    session.flush()
    return older, newer


def test_merge_keeps_history_and_the_older_profile(session):
    provision(session)
    older, newer = _pair(session)
    recruiter = session.scalar(select(User).where(User.role == "recruiter"))
    actor = Actor(kind="user", user_id=recruiter.id)
    session.commit()
    with TestClient(app) as client:
        preview = client.get(
            "/profile-merges/preview",
            params={"left_id": str(newer.id), "right_id": str(older.id)},
            headers=RECRUITER,
        )
    assert preview.status_code == 200
    body = preview.json()
    assert body["survivor_id"] == str(older.id)
    assert body["absorbed_id"] == str(newer.id)
    assert {item["display_name"] for item in body["profiles"]} == {"Ada Lovelace", "A. Lovelace"}
    session.expire_all()
    assert session.get(Candidate, newer.id).merged_into_id is None
    merged = merge_profiles(session, newer.id, older.id, actor, confirm=True)
    session.commit()
    assert merged["survivor_id"] == str(older.id)
    session.expire_all()
    kept = session.get(Candidate, older.id)
    absorbed = session.get(Candidate, newer.id)
    assert kept.display_name == "Ada Lovelace"
    assert kept.merged_into_id is None
    assert absorbed.display_name == "A. Lovelace"
    assert absorbed.merged_into_id == older.id
    assert session.scalar(select(func.count()).select_from(Candidate)) == 2
    assert session.scalar(select(func.count()).select_from(CandidateDocument)) == 2
    assert session.scalar(select(func.count()).select_from(Application)) == 2
    documents = session.scalars(select(CandidateDocument)).all()
    assert {item.candidate_id for item in documents} == {older.id}
    current = [item for item in documents if item.is_current]
    assert len(current) == 1
    assert current[0].received_at == datetime(2024, 7, 1, tzinfo=UTC)
    employers = set(
        session.scalars(select(CandidateExperience.employer).where(CandidateExperience.candidate_id == older.id))
    )
    assert employers == {"Analytical Engines", "Harbour Lab"}
    kinds = set(session.scalars(select(CandidateContact.kind).where(CandidateContact.candidate_id == older.id)))
    assert kinds == {"email", "phone"}
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "profiles_merged"))
    assert event.detail["survivor_id"] == str(older.id)
    assert event.detail["absorbed_id"] == str(newer.id)
    assert event.detail["count"] == 1
    assert "@" not in str(event.detail)


def test_unconfirmed_engineer_and_system_merge_do_nothing(session):
    provision(session)
    older, newer = _pair(session)
    engineer = session.scalar(select(User).where(User.role == "engineer"))
    session.commit()
    with pytest.raises(MergeError) as system_error:
        merge_profiles(session, older.id, newer.id, SYSTEM, confirm=True)
    assert system_error.value.code == "human_required"
    with pytest.raises(MergeError) as engineer_error:
        merge_profiles(session, older.id, newer.id, Actor(kind="user", user_id=engineer.id), confirm=True)
    assert engineer_error.value.code == "recruiter_required"
    with TestClient(app) as client:
        denied = client.post(
            "/profile-merges",
            headers=ENGINEER,
            json={"left_id": str(older.id), "right_id": str(newer.id), "confirm": True},
        )
        waiting = client.post(
            "/profile-merges",
            headers=RECRUITER,
            json={"left_id": str(older.id), "right_id": str(newer.id), "confirm": False},
        )
    assert denied.status_code == 403
    assert waiting.status_code == 422
    session.expire_all()
    assert session.get(Candidate, older.id).merged_into_id is None
    assert session.get(Candidate, newer.id).merged_into_id is None
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "profiles_merged")) is None


def test_duplicate_detection_does_not_call_merge():
    import inspect

    import app.services.excel_ops as excel_ops
    import app.services.pipeline as pipeline

    assert "merge_profiles" not in inspect.getsource(pipeline)
    assert "merge_profiles" not in inspect.getsource(excel_ops)
