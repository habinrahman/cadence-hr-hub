from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import provision
from app.domain.actor import AGENT, Actor
from app.domain.transitions import TransitionError
from app.main import app
from app.models import AuditEvent, Candidate, SharingRecord, User
from app.services.mail import OutboundEmail, get_mail_sender
from app.services.sharing import SendError, approve_candidate, send_to_company

RECRUITER = {"Authorization": "Bearer dev-recruiter-token"}
ENGINEER = {"Authorization": "Bearer dev-engineer-token"}


class FakeMail:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> None:
        if self.fail:
            raise OSError("mail down")
        self.sent.append(message)


def _recruiter(session) -> Actor:
    provision(session)
    user = session.scalar(select(User).where(User.role == "recruiter"))
    return Actor(kind="user", user_id=user.id)


def test_send_requires_a_recruiter_approval_and_records_the_result(session):
    actor = _recruiter(session)
    candidate = Candidate(source="upload", display_name="Ada Lovelace")
    session.add(candidate)
    session.commit()
    mail = FakeMail()
    with pytest_raises_send():
        send_to_company(session, candidate.id, actor, mail)
    approve_candidate(session, candidate.id, actor)
    session.commit()
    record = send_to_company(session, candidate.id, actor, mail)
    session.commit()
    assert len(mail.sent) == 1
    assert str(candidate.id) in mail.sent[0].body
    assert "ada@example.com" not in mail.sent[0].body
    assert record.destination == "smtp"
    assert record.shortlist_id is None
    saved = session.get(SharingRecord, record.id)
    assert saved.candidate_id == candidate.id
    succeeded = session.scalar(select(AuditEvent).where(AuditEvent.action == "company_send_succeeded"))
    assert succeeded.detail["candidate_id"] == str(candidate.id)
    assert "@" not in str(succeeded.detail)


def test_agent_and_engineer_cannot_send(session):
    actor = _recruiter(session)
    candidate = Candidate(source="upload")
    session.add(candidate)
    session.commit()
    approve_candidate(session, candidate.id, actor)
    session.commit()
    with pytest_raises_transition():
        send_to_company(session, candidate.id, AGENT, FakeMail())
    engineer = session.scalar(select(User).where(User.role == "engineer"))
    with pytest_raises_transition():
        send_to_company(session, candidate.id, Actor(kind="user", user_id=engineer.id), FakeMail())


def test_failed_delivery_is_audited_and_not_recorded_as_sent(session):
    actor = _recruiter(session)
    candidate = Candidate(source="upload")
    session.add(candidate)
    session.commit()
    approve_candidate(session, candidate.id, actor)
    session.commit()
    with pytest_raises_send():
        send_to_company(session, candidate.id, actor, FakeMail(fail=True))
    session.commit()
    assert session.scalar(select(SharingRecord)) is None
    failed = session.scalar(select(AuditEvent).where(AuditEvent.action == "company_send_failed"))
    assert failed.detail["error_code"] == "mail_delivery_failed"


def test_send_route_uses_the_mail_boundary(session):
    _recruiter(session)
    candidate = Candidate(source="upload")
    session.add(candidate)
    session.commit()
    mail = FakeMail()
    app.dependency_overrides[get_mail_sender] = lambda: mail
    try:
        with TestClient(app) as client:
            denied = client.post(f"/candidates/{candidate.id}/send", headers=ENGINEER)
            assert denied.status_code == 403
            missing = client.post(f"/candidates/{candidate.id}/send", headers=RECRUITER)
            assert missing.status_code == 409
            approved = client.post(f"/candidates/{candidate.id}/approvals", headers=RECRUITER)
            assert approved.status_code == 201
            sent = client.post(f"/candidates/{candidate.id}/send", headers=RECRUITER)
            assert sent.status_code == 201
            assert sent.json()["status"] == "sent"
    finally:
        app.dependency_overrides.clear()
    assert len(mail.sent) == 1
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "company_send_succeeded")) is not None


def test_missing_candidate_is_not_a_send(session):
    actor = _recruiter(session)
    with pytest_raises_send():
        approve_candidate(session, uuid4(), actor)


def pytest_raises_send():
    import pytest

    return pytest.raises(SendError)


def pytest_raises_transition():
    import pytest

    return pytest.raises(TransitionError)
