"""Render one of the four widgets live, outside Tesserae: server fetch with
the real feeds, then client.js in Chromium.

    python tools/preview.py --widget cluster [--w 800 --h 480] [key=value ...]

Settings come from the environment: OVERHEAD_CONTACT, FAL_KEY. The data dir
is tools/out/data. The page goes to tools/out/preview_<widget>.png."""

from __future__ import annotations

import argparse
import functools
import http.server
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "out"
PLACE = {"latitude": -37.67, "longitude": 144.84, "location": {"label": "Tullamarine", "timezone": "Australia/Melbourne"}}


def main() -> None:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", default="cluster", choices=("photo", "plate", "cluster", "scene"))
    ap.add_argument("--w", type=int, default=800)
    ap.add_argument("--h", type=int, default=480)
    ap.add_argument("--tag", default="")
    ap.add_argument("pairs", nargs="*")
    a = ap.parse_args()
    options = dict(PLACE)
    for pair in a.pairs:
        k, _, v = pair.partition("=")
        options[k] = json.loads(v) if v[:1] in "[{" else v
    spec = importlib.util.spec_from_file_location("overhead_widget", ROOT / f"overhead_{a.widget}" / "server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)  # type: ignore[union-attr]
    data_dir = OUT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = {"contact": os.environ.get("OVERHEAD_CONTACT", ""), "fal_api_key": os.environ.get("FAL_KEY", "")}
    data = server.fetch(options, settings, ctx={"data_dir": str(data_dir), "cell_w": a.w, "cell_h": a.h})
    print("state", data.get("state"), "error", data.get("error"), "aircraft", len(data.get("aircraft") or []), "status", data.get("status"), "notices", data.get("notices"))
    # paintings run on threads of this process: wait for them, then fetch again so the page has them
    P = server._lib("paint")
    import time

    end = time.time() + 240
    while P._PAINTING and time.time() < end:
        time.sleep(1)
    if any("painting" in s for s in (data.get("status") or [])):
        data = server.fetch(options, settings, ctx={"data_dir": str(data_dir), "cell_w": a.w, "cell_h": a.h})
        print("again:", "aircraft", len(data.get("aircraft") or []), "status", data.get("status"), "notices", data.get("notices"))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *x: None  # type: ignore[method-assign]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    (OUT / "preview_data.json").write_text(json.dumps(data), encoding="utf-8")
    html = f"""<!doctype html><html><body style="margin:0;background:#888"><div id="cell" style="width:{a.w}px;height:{a.h}px"></div>
    <script type="module">
      const m = await import('/overhead_core/static/overhead.js');
      const host = document.getElementById('cell');
      const shadow = host.attachShadow({{ mode: 'open' }});
      const data = await (await fetch('/tools/out/preview_data.json')).json();
      await m.render(shadow, {{ data, cell: {{ w: {a.w}, h: {a.h}, size: 'lg' }} }}, '{a.widget}');
      window.__done = true;
    </script></body></html>"""
    (OUT / "preview.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": a.w, "height": a.h})
        pg.on("console", lambda msg: print("  LOG", msg.type, msg.text[:200]) if msg.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: print("  PAGEERROR", str(e)[:300]))
        pg.goto(f"http://127.0.0.1:{port}/tools/out/preview.html")
        pg.wait_for_function("window.__done === true", timeout=60000)
        pg.wait_for_timeout(400)
        out = OUT / f"preview_{a.tag or a.widget}.png"
        pg.screenshot(path=str(out))
        print("wrote", out)
        b.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
