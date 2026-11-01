"""Текстовая верификация содержимого ключевых экранов."""

import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8200"


def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    for password in ("predictorlab2026", "admin"):
        page.fill('input[type="email"]', "admin@predictorlab.io")
        page.wait_for_timeout(150)
        page.fill('input[type="password"]', password)
        page.wait_for_timeout(150)
        page.click("button.btn-ink")
        page.wait_for_timeout(2000)
        if "/login" not in page.url:
            return
        inputs = page.query_selector_all('input[type="password"]')
        if len(inputs) >= 2:
            inputs[0].fill("admin")
            inputs[1].fill("predictorlab2026")
            page.wait_for_timeout(150)
            page.click("button.btn-ink")
            page.wait_for_timeout(2000)
            if "/login" not in page.url:
                return
    raise RuntimeError("Не удалось войти")


def dump(page, url, name):
    page.goto(url, wait_until="networkidle")
    time.sleep(1.2)
    text = " | ".join(page.inner_text("body").split("\n"))[:600]
    print(f"== {name} ==")
    print(text)
    print()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        login(page)
        dump(page, f"{BASE}/", "HANGAR")
        models = page.evaluate("fetch('/api/models', {credentials:'include'}).then(r => r.json())")
        ready = [m for m in models if isinstance(m, dict) and m.get("status") == "ready"]
        if ready:
            mid = ready[0]["id"]
            dump(page, f"{BASE}/m/{mid}/OVERVIEW", "OVERVIEW")
            dump(page, f"{BASE}/m/{mid}/PROFIT", "PROFIT")
            dump(page, f"{BASE}/m/{mid}/PREDICT", "PREDICT")
            dump(page, f"{BASE}/m/{mid}/CARD", "CARD")
        dump(page, f"{BASE}/new", "WIZARD")
        browser.close()


if __name__ == "__main__":
    main()
