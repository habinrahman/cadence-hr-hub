"""Browser spot-check of /demo after the scripted demo cycle (which ends with a reset, so counts are zero).

Verifies: page renders live (zero) counts, folder + file pickers exist, sidebar has the Demo / Data group,
the reset dialog gates its confirm button on the exact typed phrase, and no console errors occur.
Saves screenshots to docs/superpowers/demo-cycle/. Run from cadence-hr-hub:

    python scripts/spotcheck_demo_page.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = "http://localhost:3000"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "superpowers" / "demo-cycle"
LOG: list[str] = []


def note(text: str) -> None:
    LOG.append(text)
    print(text, flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(f"{WEB}/demo")
        page.get_by_text("Demo data").first.wait_for()

        # Live counts render (post-cycle database is empty -> zeros).
        grid = page.get_by_label("Counts from the running system")
        grid.wait_for()
        docs_stat = grid.get_by_text("Documents on record").locator("..").inner_text()
        candidates_stat = grid.get_by_text("Candidate profiles").locator("..").inner_text()
        note(f"stat 'Documents on record': {docs_stat.splitlines()[-1]}")
        note(f"stat 'Candidate profiles': {candidates_stat.splitlines()[-1]}")
        assert docs_stat.splitlines()[-1].strip() == "0", docs_stat
        assert candidates_stat.splitlines()[-1].strip() == "0", candidates_stat

        # Pickers: folder input carries webkitdirectory; both buttons exist.
        folder = page.get_by_label("Choose CV folder")
        assert folder.get_attribute("webkitdirectory") is not None, "folder input must allow directory selection"
        page.get_by_role("button", name="Choose CV folder").wait_for()
        page.get_by_role("button", name="Choose files").wait_for()
        note("folder picker (webkitdirectory) and file picker present")

        # Sidebar group.
        page.get_by_role("navigation", name="Primary").get_by_text("Demo / Data").wait_for()
        note("sidebar group 'Demo / Data' present")

        # Last reset is shown (the cycle's second reset).
        page.get_by_text("Last reset:").wait_for()
        note("last reset timestamp shown: " + page.get_by_text("Last reset:").inner_text())

        page.screenshot(path=str(OUT / "demo-page-zero-state.png"), full_page=True)
        note("screenshot demo-page-zero-state.png")

        # Reset dialog gates on the exact phrase.
        page.get_by_role("button", name="Reset demo data…").click()
        confirm = page.get_by_role("button", name="Reset demo data", exact=True)
        confirm.wait_for()
        assert confirm.is_disabled(), "confirm must start disabled"
        box = page.get_by_label("Type RESET to confirm")
        box.fill("reset")
        assert confirm.is_disabled(), "lowercase phrase must not enable confirm"
        box.fill("RESET")
        assert confirm.is_enabled(), "exact phrase must enable confirm"
        note("reset dialog gates on the exact typed phrase (disabled -> 'reset' disabled -> 'RESET' enabled)")
        page.screenshot(path=str(OUT / "demo-reset-dialog.png"))
        note("screenshot demo-reset-dialog.png")
        page.get_by_role("button", name="Cancel").click()

        real_errors = [e for e in errors if "favicon" not in e]
        assert not real_errors, f"console errors: {real_errors}"
        note(f"console errors: {len(real_errors)}")
        browser.close()
    (OUT / "spotcheck-log.txt").write_text("\n".join(LOG), encoding="utf-8")
    note("spot-check passed")


if __name__ == "__main__":
    main()
