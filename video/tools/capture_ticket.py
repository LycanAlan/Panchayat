"""Read-only: capture the earlier live case that received a real desk ticket."""
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://pcvsce443opuo4ma4wayk4bogi0btrkj.lambda-url.ap-south-1.on.aws/live/case_c46daf05df50"
OUT = Path(__file__).resolve().parents[1] / "public" / "flow"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(URL, wait_until="networkidle")
    page.get_by_role("button", name="Read it again").wait_for(timeout=120_000)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUT / "20_ticket_case_top.png"))
    page.locator(".live-filings").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "21_ticket_filing.png"))
    print(page.locator(".live-filings").inner_text()[:600])
    browser.close()
