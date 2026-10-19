"""Render film.html frame by frame: seek(t), screenshot, pipe to ffmpeg. Frame-perfect at any fps."""
import subprocess, sys, time
from playwright.sync_api import sync_playwright
fps = int(sys.argv[1]) if len(sys.argv) > 1 else 60
out = sys.argv[2] if len(sys.argv) > 2 else "film_video.mp4"
durs = sys.argv[3] if len(sys.argv) > 3 else ""
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--force-color-profile=srgb"])
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto("http://127.0.0.1:8765/film.html"); pg.wait_for_function("window.READY === true", timeout=30000)
    pg.evaluate("document.fonts.ready"); time.sleep(2)
    if durs:
        pg.evaluate(f"FILM.layout([{durs}])")
    total = pg.evaluate("FILM.total"); n = int(total * fps)
    print("frames", n, "seconds", round(total, 2), flush=True)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                           "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-tune", "film", out], stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(n):
        pg.evaluate(f"seek({i / fps})")
        ff.stdin.write(pg.screenshot(type="jpeg", quality=95))
        if i % 600 == 0:
            print(f"{i}/{n} frames · {i / max(time.time() - t0, 1e-3):.1f} fps", flush=True)
    import json
    json.dump({"starts": pg.evaluate("FILM.starts"), "total": total, "durs": pg.evaluate("FILM.durs()")}, open(out + ".json", "w"))
    ff.stdin.close(); ff.wait(); b.close()
print("done", out)
