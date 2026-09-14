"""Record the real report -> trace -> case -> sign -> ticket flow on the deployed site.

Writes ONE case to the live table (approved by the user). Everything shown is what
the deployed runtime returned. Logs each beat's time within the recording.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://pcvsce443opuo4ma4wayk4bogi0btrkj.lambda-url.ap-south-1.on.aws"
ROOT = Path(__file__).resolve().parents[1] / "public" / "flow"
ROOT.mkdir(parents=True, exist_ok=True)
REPORT = "No water in our tank for three days"

log = []
t0 = time.monotonic()


def mark(page, name, shot=True, full=False):
    t = round(time.monotonic() - t0, 2)
    if shot:
        page.screenshot(path=str(ROOT / f"{name}.png"), full_page=full)
    log.append({"beat": name, "t": t, "url": page.url})
    print(f"{t:7.2f}s  {name}  {page.url}", flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(ROOT / "video"),
                              record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page()
    t0 = time.monotonic()
    page.goto(URL + "/", wait_until="networkidle")
    page.wait_for_timeout(2000)
    mark(page, "01_home")

    field = page.locator("#intake-field")
    field.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    mark(page, "02_intake_empty")
    field.click()
    field.press_sequentially(REPORT, delay=70)
    page.select_option("#intake-segment", "ward12-4thcross")
    page.wait_for_timeout(700)
    mark(page, "03_intake_typed")

    page.get_by_role("button", name="Report it").click()
    mark(page, "04_sent", shot=False)
    page.wait_for_selector(".intake-steps .intake-step >> nth=1", timeout=120_000)
    mark(page, "05_trace_started")
    page.get_by_role("link", name="Open the live file").wait_for(timeout=120_000)
    page.wait_for_timeout(1200)
    page.locator(".intake-trace").scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    mark(page, "06_trace_done")
    trace = page.locator(".intake-trace").inner_text()
    (ROOT / "trace.txt").write_text(trace, encoding="utf-8")

    page.get_by_role("link", name="Open the live file").click()
    page.wait_for_url("**/live/**", timeout=60_000)
    page.get_by_role("button", name="Read it again").wait_for(timeout=120_000)
    page.wait_for_timeout(1500)
    mark(page, "07_case_top")
    case_id = page.url.rsplit("/", 1)[-1]

    sign = page.get_by_role("button", name="Sign as")
    sign.scroll_into_view_if_needed()
    page.wait_for_timeout(1000)
    mark(page, "08_draft_to_sign")
    sign.click()
    mark(page, "09_signing", shot=False)
    page.get_by_text("No draft is waiting for a signature").wait_for(timeout=120_000)
    page.wait_for_timeout(1500)
    mark(page, "10_signed")

    ticket = None
    for _ in range(30):
        page.wait_for_timeout(12_000)
        page.get_by_role("button", name="Read it again").click()
        page.wait_for_timeout(4_000)
        dd = page.locator("dt:text-is('Ticket') + dd").first
        text = dd.inner_text() if dd.count() else ""
        if text and "none issued" not in text and "not yet" not in text and "filing now" not in text:
            ticket = text
            break
    page.locator(".live-filings").scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    mark(page, "11_ticket")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1500)
    mark(page, "12_case_top_after")
    mark(page, "13_case_full", full=True)

    ctx.close()
    browser.close()

summary = {"case_id": case_id, "ticket": ticket, "beats": log}
(ROOT / "log.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("case", case_id, "ticket", ticket)
