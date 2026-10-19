import sys, time
from playwright.sync_api import sync_playwright
moments = [5.0, 3.0, 3.6, 3.4, 10.5, 6.5, 8.0, 6.5, 7.6, 5.5, 4.6, 6.6, 4.5, 4.0, 4.5]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome"); pg = b.new_page(viewport={"width": 1920, "height": 1080})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200])); pg.on("console", lambda m: errs.append(m.text[:200]) if m.type == "error" else None)
    import os; os.makedirs("scripts/film/board", exist_ok=True)
    pg.goto("http://127.0.0.1:8765/film.html"); pg.wait_for_function("window.READY === true", timeout=30000)
    pg.evaluate("document.fonts.ready"); time.sleep(1.5)
    starts = pg.evaluate("FILM.starts"); total = pg.evaluate("FILM.total")
    print("scenes", len(starts), "total", round(total, 1), "s")
    for i, m in enumerate(moments):
        pg.evaluate(f"seek({starts[i] + m})"); time.sleep(0.25)
        pg.screenshot(path=f"scripts/film/board/s{i:02d}.png")
    print("errors", errs)
    b.close()
