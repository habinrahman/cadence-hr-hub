from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import provision
from app.domain.actor import AGENT, Actor
from app.domain.transitions import TransitionError
from app.main import app
from app.models import AuditEvent, Candidate, SharingRecord, User
from app.services.mail import OutboundEmail, get_mail_sender
from app.services.sharing import SendError

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


def test_a_candidate_cannot_be_approved_or_sent_outside_a_request(session):
    """The only way to share is request -> confirmed pool -> shortlist -> share approval -> send."""
    _recruiter(session)
    candidate = Candidate(source="upload", display_name="Ada Lovelace")
    session.add(candidate)
    session.commit()
    mail = FakeMail()
    app.dependency_overrides[get_mail_sender] = lambda: mail
    try:
        with TestClient(app) as client:
            for headers in (RECRUITER, ENGINEER):
                for path in ("approvals", "send"):
                    assert client.post(f"/candidates/{candidate.id}/{path}", headers=headers).status_code in {404, 405}
            # The request-scoped route refuses a candidate who is not in a request's shortlist.
            fake_request = uuid4()
            assert client.post(f"/hiring-requests/{fake_request}/candidates/{candidate.id}/share", headers=RECRUITER).status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert mail.sent == []
    assert session.scalar(select(SharingRecord)) is None


def pytest_raises_send():
    import pytest

    return pytest.raises(SendError)


def pytest_raises_transition():
    import pytest

    return pytest.raises(TransitionError)
