"""Screenshot the signature features into docs/demo: the ripple map, "Neura1 remembers", "Can we promise this?",
the company sandbox and knowledge rescue. Writes to the graph (a chat message and a rescue answer), so reset the demo
afterwards (`uv run python -m neura1.cli load`).

  cd api && uv run python ../scripts/capture_signature.py [--base http://localhost:3000]
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from neura1.config import settings

OUT = Path(__file__).resolve().parents[1] / "docs" / "demo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    base = ap.parse_args().base
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark")
        ctx.add_init_script(f"localStorage.setItem('neura1-viewer','P-HITHESH');"
                            f"localStorage.setItem('neura1-passcode','{settings.demo_passcode}');"
                            "localStorage.setItem('neura1-reviewer','capture');")
        page = ctx.new_page()

        page.goto(base + "/")
        page.wait_for_selector("[data-tour=ripple] svg")
        page.wait_for_timeout(5500)
        node = page.locator("[data-tour=ripple] g[role=button]").filter(has=page.locator("circle")).nth(6)
        node.click(force=True)
        page.wait_for_timeout(1400)
        page.locator("[data-tour=ripple]").screenshot(path=str(OUT / "ripple-focus.png"))

        page.goto(base + "/chat?c=chat%2Fengineering")
        box = page.get_by_label("Message", exact=True)
        box.fill("Can we go for NB54361-L on PSM-28 to save cost?")
        page.get_by_text("Neura1 remembers").first.wait_for(timeout=15000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "remembers.png"))

        page.goto(base + "/promise")
        page.get_by_role("button", name="50 × PDU-28 by 31 Dec").click()
        page.get_by_text("Two answers to the same question").wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "promise.png"))

        page.goto(base + "/sandbox")
        page.get_by_role("button", name=re.compile("^The perfect storm")).click()
        page.get_by_text("Only when these happen together").wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "sandbox.png"))

        page.goto(base + "/rescue?person=P-SAI")
        page.get_by_text("What only Sai knows").wait_for(timeout=30000)
        page.get_by_role("button", name=re.compile("depends on NB54360")).first.click()
        page.get_by_placeholder(re.compile("Answer in your own words")).fill(
            "The power-good wait in pmic_seq.c is 6 ms since FW-233. If the regulator changes, measure soft-start on "
            "the bench at -40C and 70C with a scope on PG and VOUT. Vinay knows the rig.")
        page.get_by_role("button", name="Save as company knowledge").click()
        page.get_by_text("What Neura1 took from it").wait_for(timeout=120000)
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, 260)")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "rescue.png"))
        browser.close()
    print("wrote ripple-focus, remembers, promise, sandbox, rescue")


if __name__ == "__main__":
    main()
