"""Load a small, deterministic slice of the real CV corpus for the request-workflow demo.

Uploads the first N supported files (sorted by name) from cvs/ through the running API, then waits for the
worker to finish reading them. Nothing is fabricated: every candidate comes from a real file in cvs/.

    python scripts/seed_demo.py --count 40
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.request
import uuid
from pathlib import Path

API = "http://localhost:8000"
TOKEN = "dev-recruiter-token"
SUPPORTED = {".pdf", ".docx"}
DONE = {"extracted", "profiled", "needs_review", "needs_ocr", "failed", "quarantined", "archived"}


def _request(path: str, *, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(f"{API}{path}", data=data, headers={"Authorization": f"Bearer {TOKEN}", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read())


def _upload(path: Path) -> dict:
    boundary = uuid.uuid4().hex
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {kind}\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return _request("/documents", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parents[1] / "cvs"))
    args = parser.parse_args()
    files = sorted(p for p in Path(args.dir).iterdir() if p.suffix.lower() in SUPPORTED)[: args.count]
    ids = []
    for path in files:
        ids.append(_upload(path)["id"])
    print(f"uploaded {len(ids)} files")
    deadline = time.time() + 900
    while time.time() < deadline:
        statuses = [_request(f"/documents/{i}")["status"] for i in ids]
        pending = sum(1 for s in statuses if s not in DONE)
        print(f"  waiting on the reader: {pending} of {len(ids)} pending")
        if pending == 0:
            break
        time.sleep(5)
    else:
        print("timed out waiting for the reader", file=sys.stderr)
        return 1
    tally: dict[str, int] = {}
    for s in statuses:
        tally[s] = tally.get(s, 0) + 1
    print("document status:", tally)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
