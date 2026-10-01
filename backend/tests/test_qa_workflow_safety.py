"""Consequential actions are safe to click twice. Found in the end-to-end pass: four parallel "Approve & send" calls
sent the company four emails, and four parallel "Add to shortlist" calls opened four draft shortlists."""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import (
    ApprovalDecision,
    AuditEvent,
    CandidateDocument,
    CandidateMatch,
    CandidateSkill,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
)
from app.services.mail import OutboundEmail, get_mail_sender
from app.services.sharing import approve_share, send_share
from tests.test_mail import RECRUITER
from tests.test_sharing import _candidate, _recruiter, _request, _shortlist

PARALLEL = 4


class CountingMail:
    def __init__(self) -> None:
        self.sent: list[OutboundEmail] = []
        self._lock = Lock()

    def send(self, message: OutboundEmail) -> None:
        with self._lock:
            self.sent.append(message)


def _parallel(call):
    with ThreadPoolExecutor(PARALLEL) as pool:
        return list(pool.map(lambda _index: call(), range(PARALLEL)))


def test_parallel_approve_and_send_emails_the_company_once(session):
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    mail = CountingMail()
    app.dependency_overrides[get_mail_sender] = lambda: mail
    try:
        with TestClient(app) as client:
            base = f"/hiring-requests/{request.id}/candidates/{candidate.id}/share"
            approvals = _parallel(lambda: client.post(f"{base}/approve", headers=RECRUITER).status_code)
            sends = _parallel(lambda: client.post(base, headers=RECRUITER))
    finally:
        app.dependency_overrides.pop(get_mail_sender, None)
    assert approvals == [200] * PARALLEL
    assert {response.status_code for response in sends} == {201}
    assert len({response.json()["id"] for response in sends}) == 1, "every click returns the one sharing record"
    assert len(mail.sent) == 1
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(SharingRecord)) == 1
    assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "candidate_shared")) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "share_approved")) == 1
    del actor


def test_parallel_shortlist_clicks_open_one_shortlist(session):
    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    match = CandidateMatch(request_id=request.id, candidate_id=candidate.id, disposition="recommended")
    session.add(match)
    session.commit()
    with TestClient(app) as client:
        codes = _parallel(
            lambda: client.post(f"/hiring-requests/{request.id}/matches/{match.id}/shortlist", json={}, headers=RECRUITER).status_code
        )
    assert codes == [201] * PARALLEL
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Shortlist)) == 1
    assert session.scalar(select(func.count()).select_from(ShortlistCandidate)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "shortlist_decision")) == 1


def test_rejecting_twice_records_one_decision(session):
    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    match = CandidateMatch(request_id=request.id, candidate_id=candidate.id, disposition="needs_review")
    session.add(match)
    session.commit()
    with TestClient(app) as client:
        codes = _parallel(
            lambda: client.post(f"/hiring-requests/{request.id}/matches/{match.id}/reject", headers=RECRUITER).status_code
        )
    assert codes == [200] * PARALLEL
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "candidate_rejected")) == 1


def test_the_company_email_names_requirements_met_not_hobbies(session):
    """The email listed every parsed skill: "Poker", "Graffiti", "MLB/NBA/NFL" went to a company. It now names only
    the requirements of this request the candidate met."""
    actor = _recruiter(session)
    candidate = _candidate(session)
    document_id = session.scalar(select(CandidateDocument.id).where(CandidateDocument.candidate_id == candidate.id))
    for hobby in ("Poker", "Graffiti"):
        session.add(
            CandidateSkill(candidate_id=candidate.id, source_document_id=document_id, name=hobby, normalized_name=hobby.casefold())
        )
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    mail = CountingMail()
    approve_share(session, request.id, candidate.id, actor)
    send_share(session, request.id, candidate.id, actor, mail)
    body = mail.sent[0].body
    assert "Requirements met: Python" in body
    assert "Poker" not in body and "Graffiti" not in body


def test_parallel_create_new_candidate_clicks_create_one_profile(session):
    """Two clicks on "Create New Candidate" must not create two profiles for one CV."""
    from app.models import Candidate
    from tests.test_relationship_actions import _pending_update

    _actor, _original, incoming, review = _pending_update(session)
    before = session.scalar(select(func.count()).select_from(Candidate))
    session.commit()
    with TestClient(app) as client:
        codes = _parallel(
            lambda: client.post(
                f"/reviews/{review.id}/decision", json={"action": "create_separate_candidate"}, headers=RECRUITER
            ).status_code
        )
    assert codes == [200] * PARALLEL
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Candidate)) == before + 1
    decided = session.scalars(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided")).all()
    assert len(decided) == 1
    assert session.get(type(incoming), incoming.id).candidate_id is not None


def test_a_rejection_can_be_undone_and_the_candidate_shortlisted_again(session):
    """A mis-click on Reject was permanent: rejected candidates left the pool with no way back, and shortlisting
    one again silently returned the old rejected row."""
    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    entry = _shortlist(session, request, candidate)
    match = session.get(CandidateMatch, entry.match_id)
    session.commit()
    with TestClient(app) as client:
        base = f"/hiring-requests/{request.id}/matches/{match.id}"
        assert client.post(f"{base}/reject", headers=RECRUITER).json()["disposition"] == "rejected"
        restored = client.post(f"{base}/restore", headers=RECRUITER)
        again = client.post(f"{base}/shortlist", json={}, headers=RECRUITER)
    assert restored.status_code == 200
    # Back to what the verdicts say: the one mandatory requirement is met.
    assert restored.json()["disposition"] == "recommended"
    assert again.status_code == 201
    assert again.json()["review_state"] == "shortlisted"
    session.expire_all()
    assert session.get(ShortlistCandidate, entry.id).review_state == "shortlisted"
    actions = [row.action for row in session.scalars(select(AuditEvent).order_by(AuditEvent.created_at))]
    assert actions.count("candidate_rejected") == 1
    assert actions.count("candidate_restored") == 1
    assert "shortlist_decision" in actions


def test_engineer_cannot_restore(session):
    from tests.test_mail import ENGINEER

    _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    match = CandidateMatch(request_id=request.id, candidate_id=candidate.id, disposition="rejected")
    session.add(match)
    session.commit()
    with TestClient(app) as client:
        denied = client.post(f"/hiring-requests/{request.id}/matches/{match.id}/restore", headers=ENGINEER)
    assert denied.status_code == 403


def test_a_cv_cannot_be_merged_into_a_profile_that_was_merged_away(session):
    from app.models import Candidate
    from tests.test_relationship_actions import _pending_update

    _actor, original, _incoming, review = _pending_update(session)
    survivor = Candidate(source="upload", display_name="Survivor")
    session.add(survivor)
    session.flush()
    session.get(Candidate, original.candidate_id).merged_into_id = survivor.id
    session.commit()
    with TestClient(app) as client:
        refused = client.post(f"/reviews/{review.id}/decision", json={"action": "accept_update"}, headers=RECRUITER)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "candidate_merged"


def test_each_company_receives_its_own_shortlist_and_nothing_goes_without_a_recipient(session):
    """Every company's shortlist used to go to one configured address. Each request now names its contact;
    without one, nothing is sent."""
    from app.services.sharing import SendError

    actor = _recruiter(session)
    alpha, beta = _candidate(session, name="Alpha Person"), _candidate(session, name="Beta Person")
    request_a, request_b = _request(session), _request(session)
    request_a.company_name, request_a.contact_email = "Company A", "hiring@a.example"
    request_b.company_name, request_b.contact_email = "Company B", None
    _shortlist(session, request_a, alpha)
    _shortlist(session, request_b, beta)
    session.commit()
    mail = CountingMail()
    approve_share(session, request_a.id, alpha.id, actor)
    send_share(session, request_a.id, alpha.id, actor, mail)
    approve_share(session, request_b.id, beta.id, actor)
    try:
        send_share(session, request_b.id, beta.id, actor, mail)
        raise AssertionError("sent without a recipient")
    except SendError as exc:
        assert exc.code == "recipient_missing"
    assert [(m.to, "Company A" in m.subject, "Alpha Person" in m.body) for m in mail.sent] == [("hiring@a.example", True, True)]
    session.commit()
    with TestClient(app) as client:
        bad = client.put(f"/hiring-requests/{request_b.id}/contact", json={"contact_email": "not an email"}, headers=RECRUITER)
        good = client.put(f"/hiring-requests/{request_b.id}/contact", json={"contact_email": "Talent@B.example"}, headers=RECRUITER)
        preview = client.get(f"/hiring-requests/{request_b.id}/candidates/{beta.id}/share", headers=RECRUITER).json()
    assert bad.status_code == 422 and bad.json()["detail"] == "invalid_recipient"
    assert good.json()["contact_email"] == "talent@b.example"
    assert preview["recipient"] == "talent@b.example" and preview["company"] == "Company B"
    changed = session.scalar(select(AuditEvent).where(AuditEvent.action == "request_contact_changed"))
    assert "@" not in str(changed.detail)


def test_a_job_title_never_leaves_cadence(session):
    """A parser fragment ("financial, and humanitarian aid delivered to Ukraine (") reached a company as the title."""
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    mail = CountingMail()
    approve_share(session, request.id, candidate.id, actor)
    send_share(session, request.id, candidate.id, actor, mail)
    assert "Title" not in mail.sent[0].body and "Engineer" not in mail.sent[0].body


class BrokenMail:
    def send(self, message) -> None:
        raise ConnectionRefusedError("mail server is down")


def test_a_failed_send_is_recorded_not_counted_and_the_retry_sends_exactly_once(session):
    """Mail server down: the recruiter sees a delivery failure, nothing is recorded as shared, and the retry after the
    server returns creates one record and one email."""
    from app.models import SharingRecord
    from app.services.hiring import request_view
    from app.services.sharing import SendError

    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    approve_share(session, request.id, candidate.id, actor)
    session.commit()
    try:
        send_share(session, request.id, candidate.id, actor, BrokenMail())
        raise AssertionError("a send to a dead mail server reported success")
    except SendError as exc:
        assert exc.code == "mail_delivery_failed"
    session.commit()  # the API commits the failure audit
    assert session.scalar(select(func.count()).select_from(SharingRecord)) == 0
    assert request_view(session, request.id)["candidates_shared"] == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "candidate_share_failed")) == 1
    mail = CountingMail()
    first = send_share(session, request.id, candidate.id, actor, mail)
    session.commit()
    assert first.status == "sent" and len(mail.sent) == 1
    assert request_view(session, request.id)["candidates_shared"] == 1


def test_retrying_after_a_successful_send_returns_the_same_record_and_no_new_email(session):
    """A refresh, a second tab or an API retry after success must not email the company again."""
    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    _shortlist(session, request, candidate)
    session.commit()
    mail = CountingMail()
    approve_share(session, request.id, candidate.id, actor)
    ids = set()
    for _ in range(3):
        approve_share(session, request.id, candidate.id, actor)  # approving again is also a no-op
        ids.add(send_share(session, request.id, candidate.id, actor, mail).id)
        session.commit()
    assert len(ids) == 1
    assert len(mail.sent) == 1
    assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "candidate_shared")) == 1


def test_the_database_itself_refuses_a_second_shortlist_send_or_approval(session):
    """Backstop for the row locks: even code that skipped them could not store a duplicate."""
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from app.models import SharingRecord

    actor = _recruiter(session)
    candidate = _candidate(session)
    request = _request(session)
    entry = _shortlist(session, request, candidate)  # one draft shortlist exists
    first_send = SharingRecord(
        shortlist_id=entry.shortlist_id,
        request_id=request.id,
        candidate_id=candidate.id,
        actor_user_id=actor.user_id,
        status="sent",
        sent_at=datetime.now(timezone.utc),
        destination="smtp",
    )
    first_approval = ApprovalDecision(subject_type="share", subject_id=entry.id, decision="approved", actor_user_id=actor.user_id)
    session.add_all([first_send, first_approval])
    session.flush()

    def refused(row) -> bool:
        savepoint = session.begin_nested()
        try:
            session.add(row)
            session.flush()
        except IntegrityError:
            savepoint.rollback()
            return True
        savepoint.rollback()
        return False

    assert refused(Shortlist(request_id=request.id, status="draft"))
    assert refused(
        SharingRecord(
            shortlist_id=entry.shortlist_id,
            request_id=request.id,
            candidate_id=candidate.id,
            actor_user_id=actor.user_id,
            status="sent",
            sent_at=datetime.now(timezone.utc),
            destination="smtp",
        )
    )
    assert refused(ApprovalDecision(subject_type="share", subject_id=entry.id, decision="approved", actor_user_id=actor.user_id))
    # A failed or superseded record is history, not a second send, so it is allowed.
    assert not refused(
        SharingRecord(
            shortlist_id=entry.shortlist_id,
            request_id=request.id,
            candidate_id=candidate.id,
            actor_user_id=actor.user_id,
            status="failed",
            destination="smtp",
        )
    )


def test_each_match_states_what_was_decided_for_this_request_only(session):
    """The pool page inferred "shortlisted" from the dashboard, which stopped listing a candidate once sent: a shared
    candidate then showed "Add to shortlist" again. The server now says it per match, and per request."""
    actor = _recruiter(session)
    candidate = _candidate(session)
    request_a, request_b = _request(session), _request(session)
    entry = _shortlist(session, request_a, candidate)
    session.add(CandidateMatch(request_id=request_b.id, candidate_id=candidate.id, disposition="recommended"))
    session.commit()
    mail = CountingMail()
    app.dependency_overrides[get_mail_sender] = lambda: mail
    try:
        with TestClient(app) as client:
            def flags(request):
                match = client.get(f"/hiring-requests/{request.id}/matches", headers=RECRUITER).json()["matches"][0]
                return (match["shortlisted"], match["share_approved"], match["shared"])

            assert flags(request_a) == (True, False, False)
            client.post(f"/hiring-requests/{request_a.id}/candidates/{candidate.id}/share/approve", headers=RECRUITER)
            assert flags(request_a) == (True, True, False)
            client.post(f"/hiring-requests/{request_a.id}/candidates/{candidate.id}/share", headers=RECRUITER)
            assert flags(request_a) == (True, True, True)  # still shortlisted after it was sent
            assert flags(request_b) == (False, False, False)  # the same person is undecided on the other request
            # ...and the other request cannot share them, nor does the send count for it.
            refused = client.post(f"/hiring-requests/{request_b.id}/candidates/{candidate.id}/share", headers=RECRUITER)
            assert refused.status_code == 409
    finally:
        app.dependency_overrides.pop(get_mail_sender, None)
    assert len(mail.sent) == 1
    del actor, entry
