"""Click through the running app like a user and screenshot every step of the demo.

  cd api && uv run python ../scripts/capture_demo.py [--base http://localhost:3000]

Uses the locally installed Google Chrome through Playwright (no browser download).
Writes docs/demo/NN-name.png. Expects a freshly loaded graph (`uv run python -m neura1.cli load`).
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "demo"
NOTICE = "inbox/notice_NB54360_2026-10-14.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--passcode", default="change-me")
    args = ap.parse_args()
    base = args.base
    OUT.mkdir(parents=True, exist_ok=True)
    shots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.goto(base)
        page.evaluate(f"""() => {{ localStorage.setItem('neura1-passcode', '{args.passcode}');
                                  localStorage.setItem('neura1-reviewer', 'Kavya Menon'); }}""")

        def shot(name, full=False):
            path = OUT / f"{name}.png"
            page.wait_for_timeout(600)
            page.screenshot(path=str(path), full_page=full)
            shots.append(path.name)
            print("captured", path.name)

        # 1 Inbox
        page.goto(base)
        page.wait_for_selector("text=Supplier notice")
        shot("inbox")

        # 2 Impact from the notice (falls back to what-if if the notice has not been read)
        notices = page.evaluate("() => fetch('/api/notices').then(r => r.json())")
        has_extraction = any(n["id"] == NOTICE and n["extraction"] and not n["extraction"]["problems"]
                             for n in notices)
        url = f"{base}/impact?source={NOTICE}&as_of=2026-10-16" if has_extraction \
            else f"{base}/impact?item=NB54360&price=320&lead=22&as_of=2026-10-16"
        page.goto(url)
        page.wait_for_selector("text=Who needs to do what", timeout=60000)
        shot("impact-overview")

        # 3 Evidence behind the rejected alternate, if a decision was extracted
        src = page.locator("button:has-text('Slack')").first
        if src.count():
            src.click()
            page.wait_for_selector("text=Linked in the graph to")
            shot("evidence-slack")
            page.keyboard.press("Escape")
            page.locator("[aria-label=Close]").click()

        # 4 Department lenses
        for tab in ["Engineering", "Procurement", "Production", "Sales", "Support", "Management", "How it was computed"]:
            page.get_by_role("button", name=tab, exact=True).click()
            page.wait_for_timeout(300)
            name = "lens-" + re.sub(r"\W+", "-", tab.lower())
            page.locator("section.card").last.screenshot(path=str(OUT / f"{name}.png"))
            shots.append(f"{name}.png")
            print("captured lens", tab)

        # 5 Approve, then approve again (idempotent)
        page.get_by_role("button", name=re.compile("Approve")).click()
        page.wait_for_selector("text=tasks created")
        shot("approved")
        page.get_by_role("button", name=re.compile("Approve again")).click()
        page.wait_for_selector("text=0 tasks created")
        shot("approved-again")

        # 6 New information arrives, then the impact view shows what changed
        page.goto(base)
        page.get_by_role("button", name="Bring in the updates").click()
        page.wait_for_selector("text=new sources")
        page.goto(url)
        page.wait_for_selector("text=Who needs to do what", timeout=60000)
        shot("after-update")

        # 7 Company brain and search
        page.goto(f"{base}/brain")
        page.wait_for_selector("text=People and what they own")
        page.fill("input[placeholder^='Search everything']", "thermal shutdown")
        page.get_by_role("button", name="Search", exact=True).click()
        page.wait_for_timeout(800)
        shot("company-brain")

        # 8 Investigations history
        page.goto(f"{base}/history")
        page.wait_for_timeout(800)
        shot("investigations")

        # 9 Import: a CAD BOM with mistakes
        bad = OUT / "_kicad_bom_with_errors.csv"
        bad.write_text('"Reference","Value","Qty","Manufacturer","Manufacturer Part Number"\n'
                       '"U1,U2","Buck regulator","2","Northbridge Semi","NB54360"\n'
                       '"PS1","Power module","1","Voltline","PSU-24"\n'
                       '"C9","22uF","two","Corewind","CAP-22U-50"\n')
        page.goto(f"{base}/import")
        page.fill("input[placeholder='e.g. VC-200-C']", "VC-200-D")
        page.set_input_files("input[type=file]", str(bad))
        page.wait_for_selector("text=errors")
        shot("import-errors", full=True)
        bad.unlink()
        browser.close()
    print("\n".join(shots))


if __name__ == "__main__":
    main()
