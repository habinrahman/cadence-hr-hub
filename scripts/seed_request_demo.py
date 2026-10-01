"""Deterministic demo seed for the request workflow.

Uploads the first N CVs (sorted by filename) from ../cvs through the running API and waits until each is
processed. It only uses public endpoints, so every row goes through the normal pipeline and audit trail.
It does not create hiring requests: log the request from the UI or the API so the flow itself is exercised.

    python scripts/seed_request_demo.py [count]        # default 30
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

API = "http://localhost:8000"
HEADERS = {"Authorization": "Bearer dev-recruiter-token"}
CVS = Path(__file__).resolve().parent.parent / "cvs"
DONE = {"profiled", "extracted", "needs_review", "needs_ocr", "failed", "quarantined", "unsupported"}


def main(count: int) -> None:
    files = sorted(p for p in CVS.iterdir() if p.suffix.lower() in {".pdf", ".docx"})[:count]
    ids: list[str] = []
    with httpx.Client(base_url=API, headers=HEADERS, timeout=60) as client:
        for path in files:
            mime = "application/pdf" if path.suffix.lower() == ".pdf" else (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            response = client.post("/documents", files={"file": (path.name, path.read_bytes(), mime)})
            response.raise_for_status()
            ids.append(response.json()["id"])
        print(f"uploaded {len(ids)} CVs")
        deadline = time.time() + 600
        statuses: dict[str, str] = {}
        while time.time() < deadline:
            for doc_id in ids:
                if statuses.get(doc_id) in DONE:
                    continue
                statuses[doc_id] = client.get(f"/documents/{doc_id}").json()["status"]
            if all(statuses.get(doc_id) in DONE for doc_id in ids):
                break
            time.sleep(2)
    tally: dict[str, int] = {}
    for status in statuses.values():
        tally[status] = tally.get(status, 0) + 1
    print("final statuses:", dict(sorted(tally.items())))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
