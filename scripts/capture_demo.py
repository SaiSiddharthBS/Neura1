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
    ap.add_argument("--passcode", default=None, help="defaults to NEURA1_DEMO_PASSCODE in api/.env")
    args = ap.parse_args()
    if args.passcode is None:
        from neura1.config import settings
        args.passcode = settings.demo_passcode or ""
    base = args.base
    OUT.mkdir(parents=True, exist_ok=True)
    shots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, color_scheme="dark")
        # Screenshots are still images: show every card at rest instead of mid scroll-reveal.
        STILL = ("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');"
                 " s.textContent = 'main .card { animation: none !important; } .split-word { opacity: 1 !important; transform: none !important; filter: none !important; }'; document.head.appendChild(s); });")
        page.add_init_script(STILL)
        page.goto(base)
        page.evaluate(f"""() => {{ localStorage.setItem('neura1-passcode', '{args.passcode}');
                                  localStorage.setItem('neura1-reviewer', 'Hithesh'); }}""")

        def shot(name, full=False):
            path = OUT / f"{name}.png"
            page.wait_for_timeout(600)
            page.screenshot(path=str(path), full_page=full)
            shots.append(path.name)
            print("captured", path.name)

        # 1 Signals: what arrives at the company
        page.goto(f"{base}/signals")
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

        # 5b The workboard: move one task forward, as a person would
        page.goto(f"{base}/board")
        page.wait_for_selector("text=Process")
        # Move buttons appear when a card is hovered, as for a person using a mouse.
        card = page.locator("article", has_text="Firmware review").first
        card.hover(); page.wait_for_timeout(400)
        card.get_by_role("button", name="In progress").click()
        page.wait_for_selector("text=Moved to")
        card = page.locator("article", has_text="Confirm pricing").first
        card.hover(); page.wait_for_timeout(400)
        card.get_by_role("button", name="Done").click()
        page.wait_for_timeout(1200)
        page.evaluate("window.lenis ? window.lenis.scrollTo(0, { immediate: true }) : window.scrollTo(0, 0)")
        shot("workboard")

        # 6 New information arrives, then the impact view shows what changed
        page.goto(f"{base}/signals")
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

        # 7b The wider company brain
        page.get_by_role("button", name="Nilgiri", exact=True).click()
        page.wait_for_timeout(1500)
        page.locator("section.card").nth(1).screenshot(path=str(OUT / "who-knows.png")); shots.append("who-knows.png")
        for name, url, wait in (("people", "/people?id=P-SAI", "Working on now"),
                                ("projects", "/projects?id=PRJ-NILGIRI", "Recent discussion"),
                                ("whats-new", "/changes", "Needs attention")):
            page.goto(base + url)
            page.wait_for_selector(f"text={wait}")
            shot(name)

        # 7c Company events beyond supplier changes, and the company overview
        for name, url, wait in (("customer-escalation", "/customers?id=C-KONKAN", "Escalation plan"),
                                ("absence-plan", "/people?id=P-RAGHAVENDRA&absence=1", "Handover plan"),
                                ("risk-radar", "/risk", "How work actually clusters"),
                                ("overview", "/", "Needs attention"),
                                ("graph-explorer", "/explore?id=NB54360", "History")):
            page.goto(base + url)
            page.wait_for_selector(f"text={wait}", timeout=120000)
            page.wait_for_timeout(1500)
            shot(name)

        # The same overview in the light theme (Neura1 follows the system theme)
        light = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, color_scheme="light")
        light.add_init_script(STILL)
        light.goto(base)
        light.evaluate("() => { localStorage.setItem('neura1-viewer', 'P-HITHESH'); }")
        light.goto(base)
        light.wait_for_selector("text=Needs attention")
        light.wait_for_timeout(2500)
        light.screenshot(path=str(OUT / "overview-light.png")); shots.append("overview-light.png")
        light.close()

        # 7c2 Neura1 Chat: a slash command answered from the graph, redacted for the channel's audience
        page.goto(f"{base}/chat")
        box = page.get_by_placeholder("@neura1 to ask")
        box.wait_for(timeout=60000)
        for msg in ("Heads up: Northbridge just changed NB54360 pricing and lead time. Checking what it hits.", "/impact NB54360 320 22", "/who CAN bus"):
            box.fill(msg)
            box.press("Enter")
            page.wait_for_timeout(2500)
        page.wait_for_selector("text=PDU-28", timeout=60000)
        page.wait_for_timeout(1500)
        shot("chat")

        # 7c3 Neura1 Docs: a change notice written from the graph, a fact check, and an AI edit as tracked changes
        page.goto(f"{base}/docs")
        page.wait_for_selector("text=Engineering change notice")
        page.wait_for_timeout(1500)
        shot("docs-library")
        page.locator("button", has_text="Create from the graph").first.click()
        page.wait_for_selector(".superdoc-page", timeout=240000)
        page.wait_for_function("() => !!window.neura1Doc", timeout=120000)
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="Save").click()
        page.wait_for_selector("text=Saved · version", timeout=120000)
        shot("docs-change-notice")
        page.goto(f"{base}/docs")
        page.locator("button", has_text="Blank document").click()
        page.wait_for_selector(".superdoc-page", timeout=240000)
        page.wait_for_function("() => !!window.neura1Doc", timeout=120000)
        page.wait_for_timeout(1500)
        page.locator(".superdoc-page").first.click(position={"x": 300, "y": 160})
        page.keyboard.press("Meta+ArrowDown")
        page.keyboard.press("Enter")
        page.keyboard.type("Proposal: we will switch NB54360 to NB54361-L to cut cost, using quote Q-099. "
                           "MX-3360 is approved as a second source. Raghavendra will review PSM-28 Rev 1 before SO-889 ships.")
        page.get_by_role("button", name="Check facts").click()
        page.get_by_role("button", name="Check again").click()
        page.wait_for_selector("text=was rejected (DEC-117)", timeout=60000)
        page.wait_for_timeout(1000)
        shot("docs-fact-check")
        page.get_by_role("button", name="Edit with AI").click()
        page.locator(".superdoc-page").first.click(position={"x": 300, "y": 160})
        page.keyboard.press("Meta+ArrowDown")
        for _ in range(62):
            page.keyboard.press("Shift+ArrowLeft")
        page.get_by_role("button", name="Selection").click()
        page.get_by_role("button", name="Make it more formal").click()
        try:
            page.wait_for_function("() => !document.body.innerText.includes('Reading the graph and rewriting')", timeout=900000)
            page.wait_for_timeout(1500)
            shot("docs-ai-edit")
        except Exception:
            print("AI edit skipped: model not available")
        if page.is_closed():
            # The tab can be lost under memory pressure while the local model runs; carry on in a fresh one.
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, color_scheme="dark")
            page.add_init_script(STILL)
            page.goto(base)
            page.evaluate(f"() => {{ localStorage.setItem('neura1-passcode', '{args.passcode}'); }}")

        # 7c4 Capability map, as leadership sees it (names) and as an engineer sees it (counts only)
        page.goto(f"{base}/capabilities")
        page.wait_for_selector("text=Where Flyvi is thin")
        page.wait_for_timeout(2000)
        shot("capability-map")

        # 7d People and organisation, seen by two employees
        page.evaluate("() => localStorage.setItem('neura1-viewer', 'P-VISHWAS')")
        for name, url, wait in (("my-day", "/me", "Your work"),
                                ("organisation", "/org", "Organisation"),
                                ("employee-360", "/people?id=P-RAGHAVENDRA", "Working on now")):
            page.goto(base + url)
            page.wait_for_selector(f"text={wait}", timeout=120000)
            page.wait_for_timeout(2500)
            shot(name)
        page.evaluate("() => localStorage.setItem('neura1-viewer', 'P-ANIRUDH')")
        page.goto(f"{base}/capabilities")
        page.wait_for_selector("text=Where Flyvi is thin")
        page.wait_for_timeout(2000)
        shot("capability-map-restricted")
        page.goto(base + "/people?id=P-RAGHAVENDRA")
        page.wait_for_selector("text=Working on now")
        page.wait_for_timeout(1500)
        shot("employee-360-restricted")
        page.evaluate("() => localStorage.setItem('neura1-viewer', 'P-HITHESH')")

        # 8 Investigations history
        page.goto(f"{base}/history")
        page.wait_for_timeout(800)
        shot("investigations")

        # 9 Import: a CAD BOM with mistakes
        bad = OUT / "_kicad_bom_with_errors.csv"
        bad.write_text('"Reference","Value","Qty","Manufacturer","Manufacturer Part Number"\n'
                       '"U1,U2","Buck regulator","2","Northbridge Semi","NB54360"\n'
                       '"PS1","Power module","1","Flyvi","PSM-28"\n'
                       '"C9","22uF","two","Corewind","CAP-22U-50"\n')
        page.goto(f"{base}/import")
        page.fill("input[placeholder='e.g. PDU-28-C']", "PDU-28-D")
        page.set_input_files("input[type=file]", str(bad))
        page.wait_for_selector("text=errors")
        shot("import-errors", full=True)
        bad.unlink()
        browser.close()
    print("\n".join(shots))


if __name__ == "__main__":
    main()
