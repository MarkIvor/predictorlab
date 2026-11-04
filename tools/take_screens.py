import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8200"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PASS = "predictorlab"


def wait_ready(page):
    for _ in range(30):
        try:
            httpx.get(f"{BASE}/api/health", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[type="email"]', "admin@predictorlab.io")
    page.fill('input[type="password"]', PASS)
    page.click('button[type="submit"], button:not([type])')
    page.wait_for_timeout(2000)
    if "/login" in page.url:
        inputs = page.query_selector_all('input[type="password"]')
        if len(inputs) >= 2:
            inputs[0].fill(PASS)
            inputs[1].fill("predictorlab2026")
            page.click("button")
            page.wait_for_timeout(2000)
    page.wait_for_timeout(1000)


def shot(page, path, full=True):
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / path), full_page=full)
    print(f"  {path}")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    assert wait_ready(page), "Server not running"

    # 1. Login page
    page.goto(f"{BASE}/login", wait_until="networkidle")
    shot(page, "01_login.png")

    login(page)

    # 2. Hangar (models dashboard)
    page.goto(f"{BASE}/", wait_until="networkidle")
    shot(page, "02_hangar.png")

    # 3. Model overview
    models = page.evaluate("fetch('/api/models', {credentials:'include'}).then(r=>r.json())")
    ready = [m for m in models if isinstance(m, dict) and m.get("status") == "ready"]
    if ready:
        mid = ready[0]["id"]

        # 4. Overview with explanations
        page.goto(f"{BASE}/m/{mid}/OVERVIEW", wait_until="networkidle")
        shot(page, "03_overview.png")

        # 5. What-If
        page.goto(f"{BASE}/m/{mid}/WHAT-IF", wait_until="networkidle")
        shot(page, "04_whatif.png")

        # 6. Profit
        page.goto(f"{BASE}/m/{mid}/PROFIT", wait_until="networkidle")
        shot(page, "05_profit.png")

        # 7. Predict
        page.goto(f"{BASE}/m/{mid}/PREDICT", wait_until="networkidle")
        shot(page, "06_predict.png")

        # 8. API tab — web form
        page.goto(f"{BASE}/m/{mid}/API", wait_until="networkidle")
        shot(page, "07_api_share.png")

        # 9. Model Card
        page.goto(f"{BASE}/m/{mid}/CARD", wait_until="networkidle")
        shot(page, "08_model_card.png")

    # 10. Wizard — step 1
    page.goto(f"{BASE}/new", wait_until="networkidle")
    shot(page, "09_wizard_data.png")

    # 11. Admin
    page.goto(f"{BASE}/admin", wait_until="networkidle")
    shot(page, "10_admin.png")

    browser.close()
    print("Done!")
