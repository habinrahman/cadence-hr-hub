"""Demo-cycle validation: reset -> verify zero -> load cvs/ -> poll status -> reset -> verify zero.

Usage: python scripts/demo_cycle.py
Reads HUB_API (default http://localhost:8000) and HUB_RECRUITER_TOKEN (default dev-recruiter-token).
"""

import os
import time
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = os.environ.get("HUB_API", "http://localhost:8000")
TOKEN = os.environ.get("HUB_RECRUITER_TOKEN", "dev-recruiter-token")
CVS = Path(__file__).resolve().parents[1] / "cvs"


def call(method, path, body=None, raw=None, filename=None):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if raw is not None:
        boundary = "boundary"
        payload = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + raw + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        data = payload
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


def status():
    return call("GET", "/demo/status")


def main():
    started = time.perf_counter()
    call("POST", "/demo/reset", body={"confirm": "RESET"})
    zero = status()
    assert zero["candidates"] == 0 and zero["documents"] == 0, zero
    print(f"reset ok, zero verified ({time.perf_counter() - started:.1f}s)")

    files = [p for p in CVS.iterdir() if p.is_file()]
    print(f"{len(files)} files in cvs/")
    upload_start = time.perf_counter()
    created = failed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lambda p: _upload(p), files):
            if result == "created":
                created += 1
            elif result == "failed":
                failed += 1
    upload_s = time.perf_counter() - upload_start
    print(f"uploaded {len(files) - failed} ({created} new), failed {failed}, in {upload_s:.1f}s")

    poll_start = time.perf_counter()
    while True:
        s = status()
        if not s["processing"]:
            break
        time.sleep(3)
    process_s = time.perf_counter() - poll_start
    final = status()
    print(f"processing settled in {process_s:.1f}s")
    print(json.dumps(final, indent=2))

    call("POST", "/demo/reset", body={"confirm": "RESET"})
    zero_again = status()
    assert zero_again["candidates"] == 0 and zero_again["documents"] == 0, zero_again
    print(f"second reset ok, zero verified (total {time.perf_counter() - started:.1f}s)")


def _upload(path):
    try:
        return "created" if call("POST", "/documents", raw=path.read_bytes(), filename=path.name)["created"] else "duplicate"
    except Exception as exc:  # noqa: BLE001 - record and continue, like the browser loop
        print(f"FAILED {path.name}: {exc}")
        return "failed"


if __name__ == "__main__":
    main()
