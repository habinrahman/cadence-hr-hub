"""Dashboard counts, the work queue, and the recruiter profile read model."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import provision
from app.main import app
from app.models import (
    Application,
    ApprovalDecision,
    AuditEvent,
    Candidate,
    CandidateCertificate,
    CandidateContact,
    CandidateDocument,
    CandidateExperience,
    CandidateMatch,
    CandidateSkill,
    CandidateSource,
    DuplicateReview,
    ExtractionEvidence,
    HiringRequest,
    ProblemReport,
    RequestRequirement,
    Shortlist,
    ShortlistCandidate,
    User,
)
from tests.test_mail import ENGINEER, RECRUITER

CONTACT = "ada@example.com"
QUOTE = "Reconcile ledger accounts"


def _document(name: str, *, current: bool, candidate_id=None, supersedes=None) -> CandidateDocument:
    return CandidateDocument(
        candidate_id=candidate_id,
        sha256=name.ljust(64, "c"),
        original_filename=f"{name}.pdf",
        media_type="application/pdf",
        byte_size=24,
        storage_key=f"desk/{name}",
        status="profiled",
        is_current=current,
        supersedes_document_id=supersedes,
        processing_version=1,
        received_at=datetime(2024, 1, 1, tzinfo=UTC) if current else datetime(2020, 1, 1, tzinfo=UTC),
    )


def test_dashboard_counts_come_from_stored_rows(session):
    provision(session)
    recruiter = session.scalar(select(User).where(User.role == "recruiter"))
    ada = Candidate(source="upload", display_name="Ada Lovelace")
    grace = Candidate(source="upload", display_name="Grace Hopper")
    session.add_all([ada, grace])
    session.flush()
    session.add(
        CandidateContact(
            candidate_id=ada.id,
            kind="email",
            value_raw=CONTACT,
            value_normalized=CONTACT,
            is_primary=True,
        )
    )
    pending_doc = _document("pending", current=False)
    session.add(pending_doc)
    session.flush()
    pending = DuplicateReview(
        document_id=pending_doc.id,
        candidate_id=ada.id,
        status="pending",
        proposed_outcome="updated_cv",
        signals={"evidence": []},
    )
    decided = DuplicateReview(
        document_id=pending_doc.id,
        candidate_id=ada.id,
        status="accepted_update",
        proposed_outcome="updated_cv",
        signals={"evidence": []},
    )
    open_request = HiringRequest(
        company_name="Northwind",
        job_title="Analyst",
        description="Need an analyst.",
        status="open",
        received_at=datetime(2026, 3, 1, tzinfo=UTC),
        owner_user_id=recruiter.id,
    )
    closed_request = HiringRequest(
        company_name="Closed Co",
        job_title="Archived role",
        description="Finished.",
        status="closed",
        received_at=datetime(2025, 1, 1, tzinfo=UTC),
        owner_user_id=recruiter.id,
    )
    session.add_all([pending, decided, open_request, closed_request])
    session.flush()
    session.add(
        RequestRequirement(
            request_id=open_request.id,
            position=1,
            label="skill",
            requirement_text="Python",
            strength="mandatory",
            review_status="proposed",
        )
    )
    session.add(
        RequestRequirement(
            request_id=open_request.id,
            position=2,
            label="skill",
            requirement_text="SQL",
            strength="preferred",
            review_status="approved",
        )
    )
    waiting = CandidateMatch(request_id=open_request.id, candidate_id=ada.id, disposition="needs_review")
    placed = CandidateMatch(request_id=open_request.id, candidate_id=grace.id, disposition="recommended")
    session.add_all([waiting, placed])
    session.flush()
    shortlist = Shortlist(request_id=open_request.id, status="draft")
    session.add(shortlist)
    session.flush()
    queued_share = ShortlistCandidate(
        shortlist_id=shortlist.id,
        candidate_id=ada.id,
        match_id=waiting.id,
        review_state="shortlisted",
    )
    approved_share = ShortlistCandidate(
        shortlist_id=shortlist.id,
        candidate_id=grace.id,
        match_id=placed.id,
        review_state="shortlisted",
    )
    session.add_all([queued_share, approved_share])
    session.flush()
    session.add(
        ApprovalDecision(
            subject_type="share",
            subject_id=approved_share.id,
            decision="approved",
            actor_user_id=recruiter.id,
        )
    )
    session.add(
        ProblemReport(
            reporter_user_id=recruiter.id,
            summary="Import row needs a look",
            detail="The row is waiting.",
            status="open",
            category="data",
        )
    )
    session.add(
        ProblemReport(
            reporter_user_id=recruiter.id,
            summary="Already resolved",
            detail="Done.",
            status="resolved",
            category="other",
        )
    )
    session.add(
        AuditEvent(
            actor_kind="user",
            actor_user_id=recruiter.id,
            action="duplicate_review_opened",
            entity_type="duplicate_review",
            entity_id=pending.id,
            detail={"count": 1},
        )
    )
    session.commit()
    with TestClient(app) as client:
        recruiter_view = client.get("/dashboard", headers=RECRUITER)
        engineer_view = client.get("/dashboard", headers=ENGINEER)
        queue = client.get("/work-queue", headers=RECRUITER)
        engineer_queue = client.get("/work-queue", headers=ENGINEER)
    assert recruiter_view.status_code == 200
    counts = recruiter_view.json()["counts"]
    assert counts == {
        "relationship_reviews": 1,
        "requirements_awaiting_approval": 1,
        "matches_awaiting_review": 0,
        "shortlisted_candidates": 2,
        "shares_awaiting_approval": 1,
        "open_problem_reports": 1,
        "active_hiring_requests": 1,
    }
    assert CONTACT not in recruiter_view.text
    assert "Closed Co" not in recruiter_view.text
    assert "Northwind" in recruiter_view.text
    assert recruiter_view.json()["recent_activity"][0]["action"] == "duplicate_review_opened"
    assert engineer_view.status_code == 403
    assert engineer_view.json()["detail"] == "recruiter_required"
    assert CONTACT not in engineer_view.text
    assert engineer_queue.status_code == 403
    assert CONTACT not in engineer_queue.text
    kinds = {item["type"] for item in queue.json()["items"]}
    assert kinds == {"relationship_review", "requirement_approval", "share_approval"}
    assert all(item["href"] and item["created_at"] and item["status"] and item["subject"] for item in queue.json()["items"])
    assert not any(item["type"] == "share_approval" and "Grace Hopper" in item["subject"] for item in queue.json()["items"])
    session.expire_all()
    assert session.get(DuplicateReview, pending.id).status == "pending"


def test_match_waiting_for_review_is_queued_until_shortlist(session):
    provision(session)
    ada = Candidate(source="upload", display_name="Ada Lovelace")
    session.add(ada)
    session.flush()
    request = HiringRequest(
        company_name="Northwind",
        job_title="Analyst",
        description="Need an analyst.",
        status="open",
        received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    session.add(request)
    session.flush()
    match = CandidateMatch(request_id=request.id, candidate_id=ada.id, disposition="needs_review")
    session.add(match)
    session.commit()
    with TestClient(app) as client:
        body = client.get("/dashboard", headers=RECRUITER).json()
        queue = client.get("/work-queue", headers=RECRUITER).json()
    assert body["counts"]["matches_awaiting_review"] == 1
    assert body["counts"]["shortlisted_candidates"] == 0
    assert any(item["type"] == "match_review" and item["href"] == f"/hiring?request={request.id}" for item in queue["items"])


def test_profile_shows_history_to_recruiters_only(session):
    provision(session)
    recruiter = session.scalar(select(User).where(User.role == "recruiter"))
    candidate = Candidate(source="upload", display_name="Ada Lovelace", years_of_experience=3)
    session.add(candidate)
    session.flush()
    older = _document("older", current=False, candidate_id=candidate.id)
    session.add(older)
    session.flush()
    current = _document("current", current=True, candidate_id=candidate.id, supersedes=older.id)
    session.add(current)
    session.flush()
    session.add_all(
        [
            CandidateContact(
                candidate_id=candidate.id,
                kind="email",
                value_raw=CONTACT,
                value_normalized=CONTACT,
                is_primary=True,
            ),
            CandidateExperience(
                candidate_id=candidate.id,
                source_document_id=current.id,
                employer="Analytical Engines",
                title="Engineer",
            ),
            CandidateSkill(candidate_id=candidate.id, source_document_id=current.id, name="Python", normalized_name="python"),
            CandidateCertificate(
                candidate_id=candidate.id,
                source_document_id=current.id,
                name="CFA Level I",
                kind="certificate",
            ),
            CandidateCertificate(
                candidate_id=candidate.id,
                source_document_id=current.id,
                name="PMP",
                kind="qualification",
            ),
            Application(
                candidate_id=candidate.id,
                document_id=older.id,
                source="upload",
                received_at=datetime(2020, 1, 1, tzinfo=UTC),
            ),
            Application(
                candidate_id=candidate.id,
                document_id=current.id,
                source="excel",
                received_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            CandidateSource(
                document_id=current.id,
                candidate_id=candidate.id,
                created_by_user_id=recruiter.id,
                display_name="Ada Lovelace",
                source_type="linkedin",
                source_reference="public-profile",
            ),
            ExtractionEvidence(
                document_id=current.id,
                candidate_id=candidate.id,
                entity_type="experience",
                field_name="title",
                extracted_value="Engineer",
                source_quote=QUOTE,
                quote_verified=True,
            ),
        ]
    )
    session.commit()
    with TestClient(app) as client:
        recruiter = client.get(f"/candidates/{candidate.id}", headers=RECRUITER)
        engineer = client.get(f"/candidates/{candidate.id}", headers=ENGINEER)
    assert recruiter.status_code == 200
    body = recruiter.json()
    assert body["contacts"][0]["value"] == CONTACT
    assert body["experiences"][0]["title"] == "Engineer"
    assert body["skills"] == ["Python"]
    assert body["certificates"][0]["name"] == "CFA Level I"
    assert body["qualifications"][0]["name"] == "PMP"
    assert [item["source"] for item in body["applications"]] == ["excel", "upload"]
    current_docs = [item for item in body["documents"] if item["is_current"]]
    superseded = [item for item in body["documents"] if not item["is_current"]]
    assert len(current_docs) == 1
    assert superseded[0]["id"] == str(older.id)
    assert current_docs[0]["supersedes_document_id"] == str(older.id)
    assert body["evidence"][0]["quote"] == QUOTE
    assert body["sources"][0]["source_type"] == "linkedin"
    assert body["narrative"] == "3 years of experience. Engineer at Analytical Engines. Skills: Python"
    assert any(item["action"] == "candidate_viewed" for item in body["activity"])
    assert engineer.status_code == 403
    assert CONTACT not in engineer.text
    assert QUOTE not in engineer.text
