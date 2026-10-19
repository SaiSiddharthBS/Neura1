"""Capture the product screens the film animates (2x resolution) and the real impact data for the ripple.

  python scripts/film/shots.py --base http://localhost:3000 --api http://127.0.0.1:8000
Reset the demo first so the screens show the story's starting state.
"""
import argparse, json, shutil, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "public" / "shots"
NOTICE = "/impact?source=inbox%2Fnotice_NB54360_2026-10-14.md"

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://localhost:3000")
ap.add_argument("--api", default="http://127.0.0.1:8000")
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
shutil.copy(HERE.parents[1] / "docs" / "readme" / "logo-dark.png", HERE / "public" / "logo.png")
req = urllib.request.Request(a.api + "/api/impact/notice?source_id=inbox%2Fnotice_NB54360_2026-10-14.md", method="POST",
                             headers={"x-neura1-as": "P-HITHESH"})
(HERE / "public" / "impact.json").write_bytes(urllib.request.urlopen(req).read())

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2, color_scheme="dark")
    ctx.add_init_script("localStorage.setItem('neura1-viewer','P-HITHESH'); localStorage.setItem('neura1-tour','done');")
    pg = ctx.new_page(); pg.set_default_timeout(90000)

    def go(path, wait=3.0):
        pg.goto(a.base + path, wait_until="networkidle"); time.sleep(wait)

    def shot(name):
        pg.mouse.move(1590, 890); time.sleep(0.4); pg.screenshot(path=str(OUT / f"{name}.png")); print(name, flush=True)

    go("/", 7); shot("overview")
    go(NOTICE, 4); shot("impact")
    go("/chat", 3); pg.locator("text=engineering").first.click(); time.sleep(1.2); shot("chat_empty")
    pg.locator('textarea[aria-label="Message"]').click(); pg.keyboard.type("Can we go for NB54361-L to save cost?", delay=30); time.sleep(3); shot("chat_guard")
    go("/promise", 3); pg.locator('button:has-text("50 × PDU-28 by 31 Dec")').click(); time.sleep(4); shot("promise")
    go("/timeline", 4); pg.locator('button:has-text("Only deviations")').click(); time.sleep(1.5)
    pg.evaluate("window.scrollTo(0, document.querySelector('[data-tour=gantt]').getBoundingClientRect().top + scrollY - 120)"); time.sleep(2.5); shot("timeline")
    pg.locator('button:has-text("SO-881: 80 units")').last.click(); time.sleep(2.5); shot("timeline_why")
    go("/connect", 3); pg.locator('button:has-text("Preview changes")').click(); pg.locator("text=Preview: nothing written yet").wait_for(); time.sleep(1.5)
    pg.evaluate("window.scrollTo(0, 360)"); time.sleep(1.5); shot("connect_diff")
    pg.evaluate("window.scrollTo(0, 0)"); time.sleep(1); pg.get_by_role("switch").click(); time.sleep(2); shot("connect_on")
    pg.get_by_role("switch").click(); time.sleep(1)
    go("/sandbox", 3); pg.locator('button:has-text("The perfect storm")').click()
    pg.locator("text=Nothing here touches the real company").wait_for(state="detached"); time.sleep(2.5); shot("sandbox")
    go("/agents", 3); pg.locator('button:has-text("Run all agents")').click(); pg.locator("text=Posted").first.wait_for(timeout=120000); time.sleep(3); shot("agents")
    b.close()
