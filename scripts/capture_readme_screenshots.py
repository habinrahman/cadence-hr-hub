"""Capture the README screenshots from the running web app. Browser only; nothing is posted from this script.

    python scripts/capture_readme_screenshots.py empty        --web http://localhost:3000   # before the import
    python scripts/capture_readme_screenshots.py request      --web http://localhost:3000   # after the import
    python scripts/capture_readme_screenshots.py forms        --web http://localhost:3000

Only screens that carry no candidate data are captured: setup, the request form, the requirements review and processing
card (cropped to those sections, never the candidate pool), the empty forms, and a 390 px view. Screens that list
candidates, contacts or CV text (profile, search, review, match pool, share, audit) are NOT captured here, because the
corpus is real people's data. Capture those locally if you need them and do not commit them.
Needs `pip install playwright` and Google Chrome.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import time

from playwright.sync_api import Page, sync_playwright

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "readme")
JD = "\n".join(
    [
        "Graduate Software and Data Engineer",
        "",
        "Required skills: Python, SQL",
        "Minimum experience: 1 year",
        "Preferred skills: Excel, Java",
        "Education: Bachelor's degree",
    ]
)


def shot(page: Page, name: str, *, full: bool = True) -> None:
    os.makedirs(OUT, exist_ok=True)
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(OUT, name), full_page=full)
    print("saved", name)


def crop(page: Page, selector: str, name: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    page.locator(selector).first.screenshot(path=os.path.join(OUT, name))
    print("saved", name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["empty", "request", "forms"])
    parser.add_argument("--web", default="http://localhost:3000")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        if args.stage == "empty":
            page.goto(f"{args.web}/demo")
            page.wait_for_selector("text=Candidate Repository")
            shot(page, "01-setup-empty.png")
        elif args.stage == "request":
            page.goto(f"{args.web}/hiring?new=1")
            page.get_by_label("Company", exact=True).fill("Northwind Logistics")
            page.get_by_label("Company contact email").fill("hiring@northwind.example")
            page.get_by_label("Job title").fill("Graduate Software and Data Engineer")
            page.get_by_label("Date received").fill(datetime.date.today().isoformat())
            page.get_by_label("Candidates requested").fill("3")
            page.get_by_label("Job description").fill(JD)
            shot(page, "03-request-form.png")
            t0 = time.time()
            page.get_by_role("button", name="Log request").click()
            page.wait_for_url(re.compile(r"request="), timeout=60_000)
            t_created = time.time() - t0
            page.get_by_role("button", name="Approve requirements").wait_for(timeout=180_000)
            t_provisional = time.time() - t0
            page.wait_for_timeout(1500)
            # The sticky top bar would be drawn across a tall element crop; hide it for these two crops only.
            page.add_style_tag(content="header { display: none !important; }")
            crop(page, "#requirements", "04-requirements-review.png")
            crop(page, "[aria-label='Request processing']", "05-request-processing.png")
            t1 = time.time()
            page.get_by_role("button", name="Approve requirements").click()
            page.wait_for_function(
                "() => /Confirmed match pool/.test(document.body.innerText) && !/Re-matching on the approved requirements/.test(document.body.innerText)",
                timeout=240_000,
            )
            t_confirmed = time.time() - t1
            print(f"timings: request created {t_created:.1f}s | provisional pool {t_provisional:.1f}s | approval to confirmed pool {t_confirmed:.1f}s")
        else:
            for route, name in (("/source", "06-source-candidate.png"), ("/data", "07-excel.png"), ("/intake", "08-cv-intake.png"), ("/reports", "09-problem-reports.png")):
                page.goto(f"{args.web}{route}")
                page.wait_for_load_state("networkidle")
                if route == "/intake":
                    # The file list under the upload area shows real file names (people's names). Capture only the header and upload area.
                    page.wait_for_timeout(600)
                    page.screenshot(path=os.path.join(OUT, name), clip={"x": 248, "y": 70, "width": 1032, "height": 300})
                    print("saved", name)
                else:
                    shot(page, name)
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(f"{args.web}/demo")
            mobile.wait_for_selector("text=Candidate Repository")
            # Viewport-sized shots: a full-page capture would draw the fixed bottom tab bar in the middle of the page.
            shot(mobile, "10-setup-mobile-390.png", full=False)
            mobile.evaluate("window.scrollTo(0, 640)")
            shot(mobile, "11-setup-mobile-390-counts.png", full=False)
        browser.close()


if __name__ == "__main__":
    main()
