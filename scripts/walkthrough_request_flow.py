"""Browser walkthrough: request submission -> automatic matching -> HR filtering -> shortlist -> approval -> sharing.

Drives the running stack (web :3000, api :8000) in headless Chromium, saves screenshots, and checks the
human-decision boundary against the API and the database after each stage. Run from cadence-hr-hub:

    python scripts/walkthrough_request_flow.py
"""

from __future__ import annotations

import json
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = "http://localhost:3000"
API = "http://localhost:8000"
HEAD = {"Authorization": "Bearer dev-recruiter-token"}
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "superpowers" / ("walkthrough-final" if "--final" in sys.argv else "walkthrough")
SEND = "--send" in sys.argv
JD = "Required education: University\nPreferred skills: Python"
LOG: list[str] = []


def api(path: str):
    req = urllib.request.Request(f"{API}{path}", headers=HEAD)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def sql(query: str) -> str:
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hub", "-d", "hub", "-At", "-c", query],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def note(text: str) -> None:
    LOG.append(text)
    print(text, flush=True)


def wait_until(check, what: str, seconds: int = 60):
    end = time.time() + seconds
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for: {what}")



def verify(request_id: str, matched: int) -> None:
    """Final evidence checks against the database and API."""
    note("--- verification ---")
    requests_n = sql("select count(*) from hiring_requests")
    jobs_n = sql("select count(*) from jobs where job_type = 'process_request'")
    note(f"hiring_requests={requests_n} process_request_jobs={jobs_n}")
    assert requests_n == "1" and jobs_n == "1"
    detail = api(f"/hiring-requests/{request_id}")
    note(f"pool: {detail['processing']['matched_count']} matched / {detail['processing']['requested_count']} requested")
    assert detail["processing"]["matched_count"] == matched == 29 and detail["processing"]["requested_count"] == 5
    system = sql("select string_agg(distinct action, ',' order by action) from audit_events where actor_kind = 'system'")
    note(f"actions performed by the system actor: {system}")
    forbidden = {"shortlist_decision", "share_approved", "candidate_shared", "candidate_rejected"}
    assert not (set(system.split(",")) & forbidden), "system must not take a human decision"
    assert {"requirements_extracted", "matching_run"} <= set(system.split(","))
    sl = sql("select string_agg(distinct actor_kind, ',') || ':' || count(*) from audit_events where action = 'shortlist_decision'")
    note(f"shortlist_decision events (actor kinds:count): {sl}")
    assert sl == "user:5", sl
    ap = sql("select string_agg(distinct actor_kind, ',') || ':' || count(*) from audit_events where action = 'share_approved'")
    note(f"share_approved events (actor kinds:count): {ap}")
    assert ap == "user:1", ap
    note("all verification checks passed")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        def shot(name: str, full: bool = False):
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            note(f"screenshot {name}.png")

        # Baseline desk before the request arrives.
        before = api("/dashboard")["counts"]
        note(f"desk before: requests_received={before['requests_received']} new_matches={before['new_matches']}")

        # 1. Request submission.
        page.goto(f"{WEB}/hiring?new=1")
        page.get_by_label("Company").fill("Northwind Traders")
        page.get_by_label("Job title").fill("Platform Engineer")
        page.get_by_label("Candidates requested").fill("5")
        page.get_by_label("Job description").fill(JD)
        shot("01-request-submission")
        page.get_by_role("button", name="Log request").click()
        page.wait_for_url("**/hiring?request=*")
        request_id = page.url.split("request=")[1].split("&")[0]
        note(f"request logged: {request_id}")

        # 2. Processing (the card, before the pool is ready).
        page.get_by_text("Request received").first.wait_for()
        shot("02-processing")
        stage_now = api(f"/hiring-requests/{request_id}")["processing"]["stage"]
        note(f"stage at first paint: {stage_now}")

        # Leave the request page so the pool is not acknowledged yet, and watch the desk tile.
        page.goto(f"{WEB}/")
        wait_until(lambda: api(f"/hiring-requests/{request_id}")["processing"]["stage"] == "complete", "processing complete")
        detail = api(f"/hiring-requests/{request_id}")
        matched = detail["processing"]["matched_count"]
        note(f"processing complete: {matched} matched, requested {detail['processing']['requested_count']}, status {detail['status']}")
        assert detail["status"] == "open"
        assert all(r["review_status"] == "proposed" for r in detail["requirements"]), "requirements must stay unreviewed"

        # Boundary: automatic processing stopped before any decision for this request.
        shortlists = sql(f"select count(*) from shortlists where request_id = '{request_id}'")
        shares = sql(
            "select count(*) from sharing_records s join shortlist_candidates sc on sc.candidate_id = s.candidate_id "
            f"join shortlists sl on sl.id = sc.shortlist_id where sl.request_id = '{request_id}'"
        )
        note(f"boundary after processing: shortlists={shortlists} shares={shares}")
        assert shortlists == "0" and shares == "0"
        actors = sql("select string_agg(distinct actor_kind, ',') from audit_events where action in ('matching_run','requirements_extracted')")
        note(f"actor kinds on matching_run/requirements_extracted: {actors}")

        page.reload()
        page.get_by_text("Needs you now").wait_for()
        tile_new = api("/dashboard")["counts"]["new_matches"]
        note(f"desk new_matches while pool unopened: {tile_new}")
        assert tile_new >= 1
        shot("03-command-center-new-matches")

        # 3. Matching complete + candidate pool. Opening the request acknowledges the pool.
        page.goto(f"{WEB}/hiring?request={request_id}")
        page.get_by_text(f"{matched} candidates matched").wait_for()
        page.get_by_text("Requested: 5").wait_for()
        shot("04-matching-complete")
        wait_until(lambda: api(f"/hiring-requests/{request_id}")["pool_opened_at"], "pool_opened_at set")
        opened = api(f"/hiring-requests/{request_id}")["pool_opened_at"]
        page.reload()
        page.get_by_text("Needs you now").count()
        page.goto(f"{WEB}/hiring?request={request_id}")
        page.get_by_text(f"{matched} candidates matched").wait_for()
        time.sleep(1)
        assert api(f"/hiring-requests/{request_id}")["pool_opened_at"] == opened, "reopen must not move the stamp"
        events = sql(f"select count(*) from audit_events where action = 'pool_opened' and entity_id = '{request_id}'")
        note(f"pool_opened_at stable across reload; pool_opened audit events: {events}")
        assert events == "1"
        page.locator("#pool").scroll_into_view_if_needed()
        page.get_by_text(f"{matched} results").wait_for()
        note(f"pool shows {matched} results, same as the card ({matched} candidates matched)")
        shot("05-candidate-pool")

        # 4. HR review: filter, expand evidence.
        page.get_by_role("radio", name="Needs review").click()
        time.sleep(0.5)
        note("match status = Needs review: " + page.get_by_text(" result").first.inner_text())
        shot("06-hr-review-needs-review")
        page.get_by_role("radio", name="All").click()
        page.get_by_label("Skill").fill("sql")
        time.sleep(0.5)
        note("skill = sql: " + page.get_by_text(" result").first.inner_text())
        shot("06b-hr-review-skill-filter")
        page.get_by_label("Skill").fill("")
        assert page.get_by_label("Location").count() == 0, "location filter must stay absent: no match has a location"
        note("location filter absent (no match carries a location)")

        # 5. Shortlist selected. Nothing is preselected.
        boxes = page.get_by_role("checkbox")
        total_boxes = boxes.count()
        checked_at_start = sum(1 for i in range(total_boxes) if boxes.nth(i).is_checked())
        note(f"checkboxes: {total_boxes}, checked before any click: {checked_at_start}")
        assert checked_at_start == 0
        for i in range(min(5, total_boxes)):
            boxes.nth(i).check()
        shot("07-selection")
        page.get_by_role("button", name="Shortlist selected (5)").click()
        page.get_by_text("Shortlist updated. Nothing was shared.").wait_for(timeout=60000)
        wait_until(lambda: sql(f"select count(*) from shortlist_candidates sc join shortlists s on s.id=sc.shortlist_id where s.request_id='{request_id}'") == "5", "5 shortlisted")
        shares_after = sql("select count(*) from sharing_records")
        note(f"shortlisted: 5, shares sent: {shares_after}")
        assert shares_after == "0"
        page.get_by_text(f"Shortlisted: 5 of {matched}").wait_for()
        note(f"visible transition: {matched} matched -> Shortlisted: 5 of {matched}")
        shot("08-shortlist")

        # 6. Share approval (human, separate from send).
        review_buttons = page.get_by_role("button", name="Review share…")
        assert review_buttons.count() == 5, f"review share only for shortlisted rows, got {review_buttons.count()}"
        review_buttons.first.click()
        page.get_by_role("button", name="Approve share…").wait_for()
        shot("09-share-approval")
        send = page.get_by_role("button", name="Send email…")
        assert send.is_disabled(), "send must stay disabled until approval"
        page.get_by_role("button", name="Approve share…").click()
        page.get_by_role("button", name="Approve share", exact=True).click()
        page.get_by_text("Share approved. Sending is a separate step.").wait_for()
        assert page.get_by_role("button", name="Send email…").is_enabled()
        shot("10-share-approved-not-sent")
        note("share approved; sent so far: " + sql("select count(*) from sharing_records"))

        if SEND:
            # 7. Send is its own confirmed human step. Local mail goes to Mailpit only.
            page.get_by_role("button", name="Send email…").click()
            page.get_by_role("button", name="Send email", exact=True).click()
            wait_until(lambda: sql("select count(*) from sharing_records") == "1", "one share recorded")
            shot("11-share-sent")
            mailpit = json.loads(urllib.request.urlopen("http://localhost:8025/api/v1/messages", timeout=10).read())
            note(f"mailpit messages: {mailpit['total']}")
            assert mailpit["total"] >= 1
            senders = sql("select string_agg(distinct actor_kind, ',') from audit_events where action in ('candidate_shared','share_sent','share_approved','shortlist_decision')")
            note(f"actor kinds on shortlist/approve/share audit events: {senders}")
            assert senders == "user", senders


        else:
            # Approval must not send anything.
            sent = sql("select count(*) from sharing_records")
            box = json.loads(urllib.request.urlopen("http://localhost:8025/api/v1/messages", timeout=10).read())["total"]
            note(f"approved, not sent: sharing_records={sent}, mailpit messages={box}")
            assert sent == "0" and box == 0, "approval must not send the email"

        verify(request_id, matched)

        assert not [e for e in errors if "favicon" not in e], f"console errors: {errors}"
        note(f"console errors: {len(errors)}")
        browser.close()
    (OUT / "walkthrough-log.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
