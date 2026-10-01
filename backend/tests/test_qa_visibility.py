"""A profile HR created without a CV is findable. Found in the end-to-end pass: an Excel import reported
"created 1", and the person appeared in neither search nor the candidate list."""

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.bootstrap import provision
from app.main import app
from tests.test_mail import RECRUITER


def _workbook(*rows) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Name", "Email", "Phone"])
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_a_spreadsheet_imported_candidate_is_found_by_name_and_listed(session):
    provision(session)
    session.commit()
    with TestClient(app) as client:
        imported = client.post(
            "/excel/candidates",
            headers=RECRUITER,
            files={"file": ("leads.xlsx", _workbook(("Zelda Quartermaine", "zelda.q@example.org", "+1 415 555 0142")), "application/octet-stream")},
        )
        assert imported.status_code == 201, imported.text
        created = imported.json()["rows"][0]
        assert created["outcome"] == "created"
        found = client.get("/search", params={"name": "Zelda"}, headers=RECRUITER).json()["results"]
        listed = client.get("/candidates", headers=RECRUITER).json()
    assert [hit["candidate_id"] for hit in found] == [created["candidate_id"]]
    assert found[0]["document_id"] is None
    assert listed["total"] == 1
    assert listed["candidates"][0]["candidate_name"] == "Zelda Quartermaine"
