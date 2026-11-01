"""Скриншоты ключевых экранов PredictorLab для проверки дизайн-системы."""

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8200"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.screenshot(path=OUT / "01_login.png")
    page.fill('input[type="email"]', "admin@predictorlab.io")
    page.fill('input[type="password"]', "admin")
    page.click("button.btn-ink")
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    if "/login" in page.url:
        inputs = page.query_selector_all('input[type="password"]')
        if len(inputs) >= 2:
            inputs[0].fill("admin")
            inputs[1].fill("predictorlab2026")
        page.click("button.btn-ink")
        page.wait_for_load_state("networkidle")
    time.sleep(0.6)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        login(page)
        page.screenshot(path=OUT / "02_hangar.png", full_page=True)

        page.goto(f"{BASE}/new", wait_until="networkidle")
        page.screenshot(path=OUT / "03_wizard_data.png", full_page=True)

        models = page.request.get(f"{BASE}/api/models").json()
        ready = [m for m in models if m["status"] == "ready"]
        if ready:
            mid = ready[0]["id"]
            for tab, name in [
                ("OVERVIEW", "04_model_overview"),
                ("DRIVERS", "05_model_drivers"),
                ("WHAT-IF", "06_model_whatif"),
                ("PROFIT", "07_model_profit"),
                ("PREDICT", "08_model_predict"),
                ("API", "09_model_api"),
                ("CARD", "10_model_card"),
                ("MONITOR", "11_model_monitor"),
            ]:
                page.goto(f"{BASE}/m/{mid}/{tab}", wait_until="networkidle")
                time.sleep(1.2)
                page.screenshot(path=OUT / f"{name}.png", full_page=True)

        page.goto(f"{BASE}/admin", wait_until="networkidle")
        page.screenshot(path=OUT / "12_admin.png", full_page=True)

        (OUT / "console_errors.json").write_text(json.dumps(errors[:30], ensure_ascii=False, indent=2), encoding="utf-8")
        print("screenshots done, console errors:", len(errors))
        browser.close()


if __name__ == "__main__":
    main()
