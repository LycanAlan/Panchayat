"""Read-only captures of the deployed site for the video's UI shots."""
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://pcvsce443opuo4ma4wayk4bogi0btrkj.lambda-url.ap-south-1.on.aws"
OUT = Path(__file__).resolve().parents[1] / "public" / "site"
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.25)
    for name, path in [("home", "/"), ("process", "/process"), ("street", "/street"), ("case", "/case")]:
        page.goto(URL + path, wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / f"{name}.png"))
        print(name, page.title())
    browser.close()
