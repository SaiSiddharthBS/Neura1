"""Screenshot inventory, purchasing, forecasts, knowledge health, meetings and personal briefs into docs/demo, and
record the ripple map as an animated GIF. Writes to the graph (a meeting, a chat question), so reset the demo after.

  cd api && uv run python ../scripts/capture_next.py [--base http://localhost:3000] [--no-gif]
"""

import argparse
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "demo"


def context(browser, who: str, dark: bool = True, video: str | None = None):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark" if dark else "light",
                              record_video_dir=video, record_video_size={"width": 1440, "height": 1000} if video else None)
    ctx.add_init_script(f"localStorage.setItem('neura1-viewer','{who}');")
    return ctx


def ripple_gif(browser, base: str) -> None:
    """The overview's ripple map: the rings spreading, then a hover tracing a path, then a click focusing a record."""
    tmp = tempfile.mkdtemp()
    ctx = context(browser, "P-HITHESH", video=tmp)
    page = ctx.new_page()
    started = time.monotonic()
    page.goto(base + "/")
    page.wait_for_selector("[data-tour=ripple] svg[role=img]")   # the map itself, not an icon
    ready = time.monotonic() - started            # the GIF starts here, as the map appears
    page.wait_for_timeout(6500)
    box = page.locator("[data-tour=ripple]").bounding_box()   # measured once the page has settled
    nodes = page.locator("[data-tour=ripple] g[role=button]")
    nodes.nth(9).hover(force=True)
    page.wait_for_timeout(1600)
    nodes.nth(6).hover(force=True)
    page.wait_for_timeout(1400)
    nodes.nth(6).click(force=True)
    page.wait_for_timeout(2600)
    video = page.video.path()
    ctx.close()
    x, y, w, h = (int(round(v / 2) * 2) for v in (box["x"], box["y"], box["width"], box["height"]))
    gif = OUT / "ripple.gif"
    palette = Path(tmp) / "palette.png"
    crop = f"crop={w}:{h}:{x}:{y},fps=10,scale=760:-1:flags=lanczos"
    start = f"{ready + 0.15:.2f}"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", start, "-i", video, "-vf", f"{crop},palettegen=max_colors=96:stats_mode=diff",
                    str(palette)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", start, "-i", video, "-i", str(palette), "-lavfi",
                    f"{crop}[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", str(gif)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if shutil.which("gifsicle"):  # smaller file, same look
        subprocess.run(["gifsicle", "-O3", "--lossy=50", "--colors", "96", str(gif), "-o", str(gif)], check=True)
    print(f"ripple.gif {gif.stat().st_size // 1024} KB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--no-gif", action="store_true")
    ap.add_argument("--gif-only", action="store_true")
    args = ap.parse_args()
    base = args.base
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        if not args.no_gif:
            ripple_gif(browser, base)
        if args.gif_only:
            browser.close()
            return

        page = context(browser, "P-HITHESH").new_page()
        page.goto(base + "/inventory?item=NB54360")
        page.get_by_text("What Neura1 sees").wait_for(timeout=30000)
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT / "inventory.png"))
        page.get_by_role("button", name="Draft purchase order").click()
        page.get_by_text("Why this order").wait_for(timeout=30000)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "purchase-order.png"))
        page.keyboard.press("Escape")

        page.goto(base + "/inventory?item=KP8081")
        page.get_by_text("Outlook, next 26 weeks").wait_for(timeout=30000)
        page.wait_for_timeout(1800)
        page.locator("section", has_text="Outlook, next 26 weeks").last.screenshot(path=str(OUT / "outlook.png"))

        page.goto(base + "/knowledge")
        page.get_by_text("Buying guide: power-stage parts").wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "knowledge-health.png"))

        page.goto(base + "/meetings")
        page.get_by_role("button", name=re.compile("Try the sample")).click()
        page.get_by_text("every quote checked").wait_for(timeout=600000)
        page.reload()
        page.get_by_text("every quote checked").wait_for(timeout=60000)
        page.wait_for_timeout(1500)
        quote = page.get_by_role("button", name=re.compile(r"^“")).first
        quote.click()
        page.wait_for_timeout(2600)
        page.evaluate("document.querySelector('audio').pause()")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "meetings.png"))

        page.goto(base + "/chat")
        page.locator("aside button").filter(has_text="Good morning, Hithesh").first.click()
        page.wait_for_url(re.compile("neura1-p-hithesh"))
        box = page.get_by_label("Message", exact=True)
        box.fill("What should we order this week, and why?")
        box.press("Enter")
        page.locator("[id^='msg-chat/neura1-p-hithesh']").filter(has_text=re.compile("KP8081|NB54360")).nth(1).wait_for(timeout=300000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "neura1-chat.png"))

        light = context(browser, "P-AMBIKA", dark=False).new_page()
        light.goto(base + "/me")
        light.get_by_text("Your brief from Neura1").wait_for(timeout=30000)
        light.wait_for_timeout(1500)
        light.locator("section", has_text="Your brief from Neura1").first.screenshot(path=str(OUT / "my-brief.png"))
        browser.close()
    print("wrote inventory, purchase-order, outlook, knowledge-health, meetings, neura1-chat, my-brief")


if __name__ == "__main__":
    main()
