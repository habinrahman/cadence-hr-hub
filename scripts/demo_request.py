"""Log one received hiring request through the API and print how automatic processing went."""

from __future__ import annotations

import json
import sys
import time
import urllib.request

API = "http://localhost:8000"
H = {"Authorization": "Bearer dev-recruiter-token", "Content-Type": "application/json"}


def call(path, body=None):
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode() if body is not None else None, headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    description = sys.argv[1] if len(sys.argv) > 1 else "Required education: Bachelor\nPreferred skills: Python"
    created = call(
        "/hiring-requests",
        {
            "company": "Acme Corp",
            "job_title": "Senior Backend Engineer",
            "description": description,
            "received_at": "2026-09-30T00:00:00Z",
            "contact_email": "hiring@acme.example",
            "requested_count": 5,
        },
    )
    print("logged", created)
    for _ in range(60):
        view = call(f"/hiring-requests/{created['id']}")
        print(" ", view["status"], view["processing"])
        if view["processing"]["stage"] in ("complete", "failed"):
            break
        time.sleep(1)
    print("requirements:", [(r["text"], r["strength"], r["review_status"]) for r in view["requirements"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
