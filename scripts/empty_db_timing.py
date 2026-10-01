"""Empty-database demo timing. Nothing is pre-seeded and nothing is inserted directly.

  1. docker compose down -v, then up -d --build (the real startup flow) on an empty database.
  2. Upload every file in cvs/ through POST /documents, exactly as the UI does.
  3. Wait until the worker has finished every job.
  4. Run representative searches.
  5. Log one hiring request and time extraction and matching.

SQL is used only to observe progress and to count results. Run from cadence-hr-hub:

    python scripts/empty_db_timing.py
"""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000"
WEB = "http://localhost:3000"
HEAD = {"Authorization": "Bearer dev-recruiter-token"}
T0 = time.perf_counter()
EVENTS: list[dict] = []
OUT = ROOT / "docs" / "superpowers" / "empty-db-timing"


def now() -> float:
    return time.perf_counter() - T0


def log(event: str, **data) -> None:
    row = {"t": round(now(), 2), "event": event, **data}
    EVENTS.append(row)
    print(f"[{row['t']:8.2f}s] {event} " + " ".join(f"{k}={v}" for k, v in data.items()), flush=True)


def sql(query: str) -> str:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hub", "-d", "hub", "-At", "-F", "|", "-c", query],
        cwd=ROOT, capture_output=True, text=True,
    )
    return out.stdout.strip()


def call(path: str, *, data: bytes | None = None, headers: dict | None = None, timeout: int = 180):
    req = urllib.request.Request(f"{API}{path}", data=data, headers={**HEAD, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def upload(path: Path) -> int:
    boundary = uuid.uuid4().hex
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {kind}\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    try:
        call("/documents", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return 201
    except urllib.error.HTTPError as exc:
        return exc.code


def wait_http(url: str, what: str, seconds: int = 300) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=3).read()
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"{what} never answered")


def counts() -> dict:
    docs = sql("select status, count(*) from candidate_documents group by 1 order by 1")
    jobs = sql("select status, count(*) from jobs where job_type='extract_document' group by 1 order by 1")
    return {
        "documents": dict(line.split("|") for line in docs.splitlines() if line),
        "jobs": dict(line.split("|") for line in jobs.splitlines() if line),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in (ROOT / "cvs").iterdir() if p.is_file())
    log("corpus", files=len(files), megabytes=round(sum(p.stat().st_size for p in files) / 1e6, 1))

    # 1. Genuinely empty database, real startup flow.
    subprocess.run(["docker", "compose", "down", "-v"], cwd=ROOT, capture_output=True)
    log("stack_down_volumes_removed")
    t_up = now()
    subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=ROOT, capture_output=True)
    log("compose_up_returned", seconds=round(now() - t_up, 1))
    wait_http(f"{API}/health", "api")
    t_api = now()
    log("api_healthy", since_up_started=round(t_api - t_up, 1))
    wait_http(WEB, "web")
    log("web_answering", since_up_started=round(now() - t_up, 1))
    empty = {
        "documents": sql("select count(*) from candidate_documents"),
        "candidates": sql("select count(*) from candidates"),
        "requests": sql("select count(*) from hiring_requests"),
        "jobs": sql("select count(*) from jobs"),
    }
    log("empty_db_verified", **empty)
    assert set(empty.values()) == {"0"}, empty

    # Background monitor: progress every 10 s, and the first moment search returns anything.
    stop = threading.Event()
    first_search: dict = {}

    def monitor() -> None:
        while not stop.is_set():
            c = counts()
            log("progress", documents=c["documents"], jobs=c["jobs"])
            if "first" not in first_search:
                try:
                    t = time.perf_counter()
                    hits = call("/search?q=" + urllib.parse.quote("engineer"), timeout=60)["results"]
                    took = time.perf_counter() - t
                    if hits:
                        first_search["first"] = round(now(), 2)
                        log("search_first_non_empty", results=len(hits), latency_s=round(took, 2))
                except Exception as exc:  # noqa: BLE001
                    log("search_probe_error", error=str(exc)[:80])
            stop.wait(10)

    threading.Thread(target=monitor, daemon=True).start()

    # 2. Upload everything through the normal API.
    t_upload = now()
    codes: dict[int, int] = {}
    first_accepted = None
    slowest = (0.0, "")
    for i, path in enumerate(files, start=1):
        t = time.perf_counter()
        code = upload(path)
        took = time.perf_counter() - t
        codes[code] = codes.get(code, 0) + 1
        slowest = max(slowest, (took, path.name))
        if code == 201 and first_accepted is None:
            first_accepted = now()
            log("first_cv_accepted", since_api_healthy=round(first_accepted - t_api, 2), since_up_started=round(first_accepted - t_up, 2))
        if i % 50 == 0:
            log("uploaded", n=i)
    t_uploaded = now()
    log("all_files_uploaded", seconds=round(t_uploaded - t_upload, 1), by_http_status=codes, slowest_upload=f"{slowest[0]:.2f}s {slowest[1]}")

    # 3. Wait for the worker to finish every job.
    while True:
        c = counts()
        active = sum(int(v) for k, v in c["jobs"].items() if k in ("queued", "leased", "running"))
        if active == 0 and sum(int(v) for v in c["jobs"].values()) > 0:
            break
        time.sleep(3)
    t_done = now()
    log("all_jobs_finished", since_first_upload=round(t_done - t_upload, 1), since_upload_complete=round(t_done - t_uploaded, 1), since_up_started=round(t_done - t_up, 1))
    stop.set()

    final = {
        "documents_total": sql("select count(*) from candidate_documents"),
        "documents_by_status": counts()["documents"],
        "jobs_by_status": counts()["jobs"],
        "candidates": sql("select count(*) from candidates"),
        "candidates_with_profiled_document": sql("select count(distinct candidate_id) from candidate_documents where status='profiled'"),
        "duplicate_update_reviews_pending": sql("select count(*) from duplicate_reviews where status='pending'"),
        "duplicate_update_reviews_total": sql("select count(*) from duplicate_reviews"),
        "quarantine_records": sql("select count(*) from quarantine_records"),
        "needs_ocr_documents": sql("select count(*) from candidate_documents where status='needs_ocr'"),
        "failed_documents": sql("select count(*) from candidate_documents where status in ('failed','quarantined')"),
        "job_attempts_over_1": sql("select count(*) from jobs where attempts > 1"),
    }
    log("final_counts", **final)

    # 4. Search is usable once the corpus is loaded. Time real queries.
    queries = [
        ("free text", {"q": "investment banking analyst"}),
        ("free text", {"q": "python machine learning"}),
        ("skill filter", {"skill": "sql"}),
        ("education filter", {"education": "University of California"}),
        ("name", {"name": "Aaron"}),
    ]
    searches = []
    for label, params in queries:
        timings = []
        results = 0
        for _ in range(2):
            t = time.perf_counter()
            hits = call("/search?" + urllib.parse.urlencode(params), timeout=120)["results"]
            timings.append(round(time.perf_counter() - t, 2))
            results = len(hits)
        searches.append({"kind": label, "params": params, "results": results, "cold_s": timings[0], "warm_s": timings[1]})
        log("search", kind=label, params=params, results=results, cold_s=timings[0], warm_s=timings[1])
    t = time.perf_counter()
    listing = call("/candidates?limit=25&offset=0", timeout=120)
    log("candidate_directory", total=listing["total"], seconds=round(time.perf_counter() - t, 2))

    # 5. One hiring request, timed by polling every 100 ms.
    body = json.dumps(
        {
            "company": "Acme Corp",
            "job_title": "Senior Backend Engineer",
            "description": "Required education: University\nPreferred skills: Python",
            "received_at": "2026-09-30T00:00:00Z",
            "contact_email": "hiring@acme.example",
            "requested_count": 5,
        }
    ).encode()
    t_submit = time.perf_counter()
    created = call("/hiring-requests", data=body, headers={"Content-Type": "application/json"})
    t_ack = time.perf_counter() - t_submit
    rid = created["id"]
    log("request_submitted", api_response_s=round(t_ack, 2), status=created["status"])
    seen_stage = None
    t_req = t_match = None
    while True:
        view = call(f"/hiring-requests/{rid}")
        elapsed = time.perf_counter() - t_submit
        stage = view["processing"]["stage"]
        if stage != seen_stage:
            log("request_stage", stage=stage, seconds_since_submit=round(elapsed, 2))
            seen_stage = stage
        if t_req is None and view["requirements"]:
            t_req = elapsed
            log("requirements_visible", seconds_since_submit=round(elapsed, 2), count=len(view["requirements"]))
        if stage in ("complete", "failed"):
            t_match = elapsed
            break
        if elapsed > 300:
            break
        time.sleep(0.1)
    request_result = {
        "submit_to_requirements_s": round(t_req, 2) if t_req is not None else None,
        "requirements_to_pool_s": round(t_match - t_req, 2) if t_req is not None and t_match is not None else None,
        "submit_to_match_complete_s": round(t_match, 2) if t_match is not None else None,
        "stage": seen_stage,
        "matched": view["processing"]["matched_count"],
        "requested": view["processing"]["requested_count"],
        "status": view["status"],
    }
    log("request_result", **request_result)

    report = {
        "events": EVENTS,
        "final": final,
        "search_first_non_empty_at_s": first_search.get("first"),
        "searches": searches,
        "request": request_result,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log("report_written", path=str(OUT / "report.json"))


if __name__ == "__main__":
    main()
