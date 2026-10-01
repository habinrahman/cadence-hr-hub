"""Drives the real /demo page in Chrome: picks files from cvs/, clicks Load, waits for the upload to finish.

Browser only: the page is the client, nothing is posted from this script.
    python scripts/browser_import_check.py one|five|full [--web http://localhost:3000] [--mobile]
Needs `pip install playwright` and Google Chrome. Prints what the page itself reports.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

CVS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cvs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["one", "five", "full"])
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--mobile", action="store_true", help="390px viewport")
    args = parser.parse_args()

    failed_requests: list[str] = []
    statuses: dict[int, int] = {}
    console_errors: list[str] = []
    started = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 390, "height": 844} if args.mobile else {"width": 1280, "height": 900})
        page.on("requestfailed", lambda r: failed_requests.append(f"{r.method} {r.url} {r.failure}"))
        page.on("response", lambda r: statuses.__setitem__(r.status, statuses.get(r.status, 0) + 1) if r.request.method == "POST" else None)
        page.on("console", lambda m: console_errors.append(m.text[:200]) if m.type == "error" else None)
        page.goto(f"{args.web}/demo")
        page.wait_for_selector("input[aria-label='Choose CV folder']", state="attached")
        if args.mode == "full":
            page.set_input_files("input[aria-label='Choose CV folder']", os.path.abspath(CVS))
        else:
            names = sorted(n for n in os.listdir(CVS) if not n.startswith("."))[: 1 if args.mode == "one" else 5]
            page.set_input_files("input[aria-label='Choose CV files']", [os.path.abspath(os.path.join(CVS, n)) for n in names])
        page.get_by_role("button", name=re.compile(r"^(Load|Import) ")).click()
        page.wait_for_function(
            "() => { const b = document.querySelector('[role=progressbar]'); return b && b.getAttribute('aria-valuenow') === b.getAttribute('aria-valuemax'); }",
            timeout=900_000,
        )
        # Wait for the worker: the upload block says "Import complete" (or reports a failure).
        page.wait_for_function(
            "() => /Import complete|Upload failed\\.|Finished with/.test(document.querySelector('[aria-label=\"This upload\"]')?.innerText ?? '')",
            timeout=1_800_000,
        )
        block = page.locator("[aria-label='This upload']").inner_text().replace("\n", " | ")
        print("PAGE SAYS:", block)
        print("POST /documents statuses:", statuses)
        print("failed requests:", len(failed_requests), failed_requests[:3])
        print("console errors:", console_errors[:3])
        print(f"wall time: {time.time() - started:.0f}s")
        page.screenshot(path="import-check.png", full_page=True)
        browser.close()
    return 0 if "Import complete" in block and not failed_requests else 1


if __name__ == "__main__":
    sys.exit(main())
