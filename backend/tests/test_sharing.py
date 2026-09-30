"""A shortlisted candidate is shared only after a recruiter approves the send."""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import provision
from app.config import get_settings
from app.domain.actor import SYSTEM, Actor
from app.domain.transitions import TransitionError
from app.main import app
from app.models import (
    AuditEvent,
    Candidate,
    CandidateContact,
    CandidateDocument,
    CandidateExperience,
    CandidateSkill,
    HiringRequest,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
    User,
)
from app.services.mail import GraphMailSender, MailUnavailable, OutboundEmail, SesMailSender, get_mail_sender
from app.services.sharing import SendError, approve_candidate, approve_share, send_share
from tests.test_mail import ENGINEER, RECRUITER, FakeMail

SECRET = "raw cv paragraph that must stay inside cadence"
CONTACT = "quinn@example.com"


def _recruiter(session) -> Actor:
    provision(session)
    user = session.scalar(select(User).where(User.role == "recruiter"))
    return Actor(kind="user", user_id=user.id)


def _candidate(session, *, name: str = "Quinn Backend") -> Candidate:
    candidate = Candidate(source="upload", display_name=name, summary=SECRET, years_of_experience=4)
    session.add(candidate)
    session.flush()
    document = CandidateDocument(
        candidate_id=candidate.id,
        sha256="ab" * 32,
        original_filename="quinn.pdf",
        media_type="application/pdf",
        byte_size=128,
        storage_key="synthetic/quinn.pdf",
        status="profiled",
        is_current=True,
        processing_version=1,
        received_at=datetime.now(timezone.utc),
    )
    session.add(document)
    session.flush()
    session.add(CandidateContact(candidate_id=candidate.id, kind="email", value_raw=CONTACT, value_normalized=CONTACT))
    session.add(
        CandidateExperience(
            candidate_id=candidate.id,
            source_document_id=document.id,
            employer="Example Labs",
            title="Engineer",
            description=SECRET,
        )
    )
    session.add(
        CandidateSkill(
            candidate_id=candidate.id,
            source_document_id=document.id,
            name="Python",
            normalized_name="python",
        )
    )
    session.flush()
    return candidate


def _request(session) -> HiringRequest:
    owner = session.scalar(select(User).where(User.role == "recruiter"))
    row = HiringRequest(
        company_name="Example Labs",
        job_title="Backend engineer",
        description="Synthetic request",
        status="open",
        received_at=datetime.now(timezone.utc),
        owner_user_id=owner.id,
    )
    session.add(row)
    session.flush()
    return row


def _shortlist(session, request, candidate) -> ShortlistCandidate:
    user = session.scalar(select(User).where(User.role == "recruiter"))
    shortlist = Shortlist(request_id=request.id, status="draft")
    session.add(shortlist)
    session.flush()
    entry = ShortlistCandidate(
        shortlist_id=shortlist.id,
        candidate_id=candidate.id,
        added_by_user_id=user.id,
        review_state="shortlisted",
    )
    session.add(entry)
    session.flush()
    return entry


def test_non_shortlisted_candidate_cannot_be_shared(session):
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    session.commit()
    with pytest.raises(SendError) as caught:
        send_share(session, request.id, candidate.id, actor, FakeMail())
    assert caught.value.code == "not_shortlisted"


def test_share_without_approval_fails(session):
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    approve_candidate(session, candidate.id, actor)
    session.commit()
    mail = FakeMail()
    with pytest.raises(SendError) as caught:
        send_share(session, request.id, candidate.id, actor, mail)
    assert caught.value.code == "approval_required"
    assert mail.sent == []
    assert session.scalar(select(func.count()).select_from(SharingRecord)) == 0


def test_engineer_cannot_send_a_share(session):
    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    with TestClient(app) as client:
        denied = client.post(
            f"/hiring-requests/{request.id}/candidates/{candidate.id}/share",
            headers=ENGINEER,
        )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "recruiter_required"


def test_system_actor_cannot_share(session):
    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    entry = _shortlist(session, request, candidate)
    session.commit()
    with pytest.raises(TransitionError) as caught:
        send_share(session, request.id, candidate.id, SYSTEM, FakeMail())
    assert caught.value.code == "human_required"
    assert session.get(Shortlist, entry.shortlist_id).status == "draft"


def test_approved_share_records_the_send_and_an_audit_event(session):
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    entry = _shortlist(session, request, candidate)
    session.commit()
    mail = FakeMail()
    approve_share(session, request.id, candidate.id, actor)
    record = send_share(session, request.id, candidate.id, actor, mail)
    session.commit()
    assert record.status == "sent"
    assert record.recipient == "company@localhost"
    assert record.request_id == request.id
    assert record.candidate_id == candidate.id
    assert record.shortlist_id == entry.shortlist_id
    assert record.actor_user_id == actor.user_id
    assert record.sent_at is not None
    assert len(mail.sent) == 1
    assert CONTACT not in mail.sent[0].body
    assert SECRET not in mail.sent[0].body
    assert "Python" in mail.sent[0].body
    saved = session.get(SharingRecord, record.id)
    assert saved.status == "sent"
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "candidate_shared"))
    assert audit.entity_id == record.id
    assert audit.detail["request_id"] == str(request.id)
    assert audit.detail["candidate_id"] == str(candidate.id)
    rendered = json.dumps(audit.detail)
    assert SECRET not in rendered
    assert "@" not in rendered
    assert session.get(Shortlist, entry.shortlist_id).status == "draft"


def test_mailpit_receives_the_approved_share(session):
    actor = _recruiter(session)
    candidate = _candidate(session, name="Quinn Mail")
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    approve_share(session, request.id, candidate.id, actor)
    record = send_share(session, request.id, candidate.id, actor, get_mail_sender())
    session.commit()
    message = _mailpit_message(str(candidate.id))
    assert record.recipient == "company@localhost"
    assert message["Subject"] == f"Shortlisted candidate {candidate.id}"
    assert message["To"][0]["Address"] == "company@localhost"
    assert CONTACT not in message["Text"]
    assert SECRET not in message["Text"]


def test_duplicate_share_returns_the_same_record(session):
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    mail = FakeMail()
    approve_share(session, request.id, candidate.id, actor)
    first = send_share(session, request.id, candidate.id, actor, mail)
    second = send_share(session, request.id, candidate.id, actor, mail)
    session.commit()
    assert first.id == second.id
    assert len(mail.sent) == 1
    assert session.scalar(select(func.count()).select_from(SharingRecord)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "candidate_shared")) == 1


def test_graph_and_ses_senders_do_not_deliver():
    message = OutboundEmail(to="company@localhost", subject="unused", body="unused")
    with pytest.raises(MailUnavailable):
        GraphMailSender().send(message)
    with pytest.raises(MailUnavailable):
        SesMailSender().send(message)


def test_local_environment_blocks_a_non_smtp_destination():
    settings = get_settings()
    previous = settings.mail_destination
    settings.mail_destination = "graph"
    try:
        with pytest.raises(MailUnavailable) as caught:
            get_mail_sender()
        assert caught.value.code == "external_mail_blocked"
    finally:
        settings.mail_destination = previous


def _mailpit_message(token: str) -> dict:
    query = urllib.parse.urlencode({"query": token})
    with urllib.request.urlopen(f"http://127.0.0.1:8025/api/v1/search?{query}", timeout=5) as response:
        payload = json.load(response)
    matches = [item for item in payload["messages"] if token in item.get("Subject", "")]
    assert matches, "Mailpit did not receive the share"
    message_id = matches[0]["ID"]
    with urllib.request.urlopen(f"http://127.0.0.1:8025/api/v1/message/{message_id}", timeout=5) as response:
        return json.load(response)
