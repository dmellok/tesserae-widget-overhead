"""Offline tests for the Overhead bundle: the feeds, the photographs, the
paintings and the four pages, with every call on the network answered here."""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cluster = _load(ROOT / "overhead_cluster" / "server.py", "overhead_cluster_server")
photo = _load(ROOT / "overhead_photo" / "server.py", "overhead_photo_server")
plate = _load(ROOT / "overhead_plate" / "server.py", "overhead_plate_server")
scene = _load(ROOT / "overhead_scene" / "server.py", "overhead_scene_server")
core = _load(ROOT / "overhead_core" / "server.py", "overhead_core_server")
S = cluster._lib("sheet")
A = S.A
P = S.P
N = S.N

MELBOURNE = {"latitude": -37.67, "longitude": 144.84, "location": {"label": "Tullamarine", "timezone": "Australia/Melbourne"}}
SETTINGS = {"fal_api_key": "k", "contact": "tester@example.com", "gen_daily_cap": "24"}
AC = [
    {"hex": "7c6b2f", "flight": "JST772 ", "r": "VH-VWN", "t": "A321", "alt_baro": 3600, "baro_rate": 992, "gs": 297, "track": 284, "lat": -37.55, "lon": 144.70, "category": "A3"},
    {"hex": "7c4b1a", "flight": "QLK1997", "r": "VH-XVQ", "t": "E190", "alt_baro": 200, "baro_rate": 2688, "gs": 145, "track": 352, "lat": -37.66, "lon": 144.84, "category": "A3"},
    {"hex": "7c7f00", "flight": "RXA3558", "r": "VH-ZJS", "t": "SF34", "alt_baro": 2050, "baro_rate": 0, "gs": 177, "track": 22, "lat": -37.78, "lon": 144.84, "category": "A2"},
    {"hex": "7c0001", "flight": "VH-NPS", "r": "VH-NPS", "t": "C172", "alt_baro": 1500, "baro_rate": 0, "gs": 72, "track": 47, "lat": -37.85, "lon": 144.9, "category": "A1"},
    {"hex": "780abc", "flight": "CRK035", "r": "B-LHP", "t": "A333", "alt_baro": "ground", "gs": 12, "track": 352, "lat": -37.67, "lon": 144.843, "category": "A5"},
    {"hex": "7c9999", "flight": "FAR999", "r": "VH-FAR", "t": "B738", "alt_baro": 30000, "gs": 450, "track": 90, "lat": -36.5, "lon": 146.5, "category": "A3"},
    {"hex": "7cnolat", "flight": "NOPOS", "t": "A320", "alt_baro": 5000},
]


def _jpeg(w=600, h=400, blob=True, paper=(255, 255, 255)) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), paper)
    if blob:
        d = ImageDraw.Draw(im)
        d.ellipse((120, 150, 480, 250), fill=(180, 40, 40))
        d.polygon([(250, 200), (330, 120), (360, 200)], fill=(60, 60, 70))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def _png_logo() -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((20, 60, 380, 140), fill=(200, 20, 20, 255))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def offline(monkeypatch):
    """Every call on the network, answered here; the prompts fal.ai got."""
    prompts: list[dict] = []
    uas: list[str] = []

    def fake_http(url, token="", accept="application/json", *, auth_scheme="Bearer", body=None, timeout=10, detail=False, ua=""):
        uas.append(ua)
        if "api.adsb.lol" in url:
            return json.dumps({"ac": AC, "now": int(time.time() * 1000)}).encode(), None
        if "aircraft.json" in url:
            return json.dumps({"aircraft": AC[:2]}).encode(), None
        if "api.adsbdb.com" in url:
            cs = url.rsplit("/", 1)[1]
            routes = {"JST772": ("Jetstar Airways", "MEL", "Melbourne", "ADL", "Adelaide"), "RXA3558": ("Regional Express", "BWT", "Burnie", "MEL", "Melbourne"), "CRK035": ("Hong Kong Airlines", "HKG", "Hong Kong", "MEL", "Melbourne")}
            if cs in routes:
                a, o, oc, d, dc = routes[cs]
                return json.dumps({"response": {"flightroute": {"airline": {"name": a}, "origin": {"iata_code": o, "municipality": oc}, "destination": {"iata_code": d, "municipality": dc}}}}).encode(), None
            return None, "HTTP 404"
        if "api.planespotters.net" in url:
            if "tester@example.com" not in ua:
                return None, "auth"
            reg = url.rsplit("/", 1)[1]
            if reg == "VH-NPS":
                return json.dumps({"photos": []}).encode(), None
            return json.dumps({"photos": [{"thumbnail": {"src": f"https://t.example/{reg}_s.jpg", "size": {"width": 200, "height": 133}}, "thumbnail_large": {"src": f"https://t.example/{reg}.jpg", "size": {"width": 498, "height": 280}}, "photographer": "A. Spotter", "link": f"https://www.planespotters.net/photo/1/{reg}"}]}).encode(), None
        if "t.example" in url:
            return _jpeg(), None
        if "fal.run" in url:
            prompts.append(json.loads(body))
            assert token == "k" and auth_scheme == "Key"
            return json.dumps({"images": [{"url": "https://fal.example/out.jpg"}]}).encode(), None
        if "fal.example" in url:
            return _jpeg(paper=(252, 250, 246)), None
        if "daisycon" in url or "kiwi" in url:
            return _png_logo(), None
        return None, "unreachable"

    monkeypatch.setattr(N, "http", fake_http)
    monkeypatch.setattr(P, "_PARALLEL", 3)
    yield prompts, uas
    with P._LOCK:
        P._QUEUE.clear()
        P._PAINTING.clear()
        P._WORKERS = 0


def _settle(timeout=10.0):
    end = time.time() + timeout
    while P._PAINTING and time.time() < end:
        time.sleep(0.02)
    assert not P._PAINTING


def _ctx(tmp_path, **kw):
    return {"data_dir": str(tmp_path), "cell_w": 800, "cell_h": 480, **kw}


# ----------------------------------------------------------------------
def test_manifests_and_client_files():
    for wid in ("overhead_core", "overhead_photo", "overhead_plate", "overhead_cluster", "overhead_scene"):
        m = json.loads((ROOT / wid / "plugin.json").read_text(encoding="utf-8"))
        assert m["version"] == "0.1.0" and m["tesserae_compat"] == "1.x"
        if wid != "overhead_core":
            assert (ROOT / wid / "client.js").exists() and m["kind"] == "widget"
            names = [o["name"] for o in m["cell_options"]]
            assert len(names) == len(set(names)) and "location" in names and "logos" in names
            assert "settings:plugin/overhead_core" in m["requires"]
    custom = next(o for o in json.loads((ROOT / "overhead_cluster" / "plugin.json").read_text())["cell_options"] if o["name"] == "custom_style")
    assert custom["type"] == "textarea" and len(custom["presets"]) >= 5


def test_nearby_filters_sorts_and_names(tmp_path, offline):
    rows, err = A.nearby("adsb_lol", "", -37.67, 144.84, 35, tmp_path, "ua")
    assert err is None
    assert [r["cs"] for r in rows] == ["CRK035", "QLK1997", "RXA3558", "JST772", "VH-NPS"], "within 35 km, nearest first; no position, no row"
    jet = next(r for r in rows if r["cs"] == "JST772")
    assert jet["typ"] == "Airbus A321" and jet["cls"] == "jet" and jet["span"] == 35.8 and jet["km"] > 10 and jet["dir"] in range(280, 340)
    assert next(r for r in rows if r["cs"] == "CRK035")["ground"] is True
    assert A.airline_of("JST772", "VH-VWN") == ("JQ", "Jetstar") and A.airline_of("VH-NPS", "VH-NPS") == ("", "private")
    assert A.airline_of("ABC123", "X", "Some Air") == ("", "Some Air")
    # a receiver of your own: its aircraft.json
    rows2, err2 = A.nearby("receiver", "pi.local:8080", -37.67, 144.84, 35, tmp_path, "ua")
    assert err2 is None and len(rows2) == 2
    assert A.nearby("receiver", "", -37.67, 144.84, 35, tmp_path, "ua")[1].startswith("Give the receiver")


def test_photo_page_has_the_airframe_photograph_and_a_strip(tmp_path, offline):
    r = photo.fetch({**MELBOURNE, "strip": "3", "logos": "on"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "ok" and r["widget"] == "photo"
    assert [a["cs"] for a in r["aircraft"]] == ["QLK1997", "RXA3558", "JST772", "VH-NPS"], "the ground stays off unless asked"
    hero = r["aircraft"][0]
    assert hero["pic"]["kind"] == "photo" and hero["pic"]["src"].startswith("data:image/jpeg") and "A. Spotter" in hero["pic"]["credit"]
    assert hero["iata"] == "QF" and hero["logo"].startswith("data:image/png")
    assert hero["route_text"] == "climbing out" and hero["alt_text"] == "200 ft climbing"
    assert r["aircraft"][2]["route_text"] == "Melbourne to Adelaide" and r["aircraft"][1]["route_text"] == "Burnie to Melbourne"
    assert r["aircraft"][3]["pic"] is None, "no photograph on planespotters: nothing to show but the silhouette"
    assert r["aircraft"][3]["sil"].endswith("light.svg")
    assert any("planespotters" in c for c in r["credits"]) and r["attribution"].startswith("positions from adsb.lol")


def test_planespotters_needs_the_contact(tmp_path, offline):
    r = photo.fetch(MELBOURNE, {"contact": ""}, ctx=_ctx(tmp_path))
    assert all(a["pic"] is None for a in r["aircraft"]), "refused without a contact in the User-Agent"
    assert any("tesserae-overhead" in u for u in offline[1])


def test_cluster_paints_from_the_photograph_and_cuts_out(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "style": "poster", "count": "4"}
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert len(prompts) == 3, "the three with a photograph; the Cessna has none"
    p = prompts[0]
    assert p["image_urls"] == ["https://t.example/VH-XVQ.jpg"] and "Embraer E190" in p["prompt"] and "VH-XVQ" in p["prompt"] and "QantasLink livery" in p["prompt"]
    assert "vintage mid-century airline poster" in p["prompt"] and "plain, pure white paper" in p["prompt"] and "contour line" in p["prompt"]
    assert r["status"] and "painting" in r["status"][0] and r["live_refresh_s"] > 0
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    painted = [a for a in r["aircraft"] if a["pic"] and a["pic"]["kind"] == "painting"]
    assert len(painted) == 3 and all(a["pic"]["src"].startswith("data:image/png") and not a["pic"]["whole"] for a in painted)
    gen = tmp_path / "gen"
    key = P.key_for("VH-XVQ", "poster")
    assert key == "vh_xvq--poster--p1" and (gen / f"{key}.jpg").exists() and (gen / f"{key}_cut.png").exists()
    meta = json.loads((gen / f"{key}.json").read_text())
    assert meta["reg"] == "VH-XVQ" and "A. Spotter" in meta["credit"]
    assert r["aircraft"][3]["pic"] is None and r["live_refresh_s"] == 0
    assert P.budget_used(gen) == 3
    # the dashboard's record for Render now
    d = S.dashboards(tmp_path)
    assert d and d[0]["name"] == "Hall" and len(d[0]["jobs"]) == 3
    # unpainted left off: the Cessna goes
    r = cluster.fetch({**options, "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert [a["cs"] for a in r["aircraft"]] == ["QLK1997", "RXA3558", "JST772"]


def test_previews_hold_and_a_new_look_drops_the_old(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "style": "woodblock", "count": "3"}
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, preview=True))
    _settle()
    assert not prompts and len(S.held(tmp_path)) == 3 and "waiting for Paint now" in r["status"][0] and r["live_refresh_s"] > 0
    cluster.fetch({**options, "style": "linocut"}, SETTINGS, ctx=_ctx(tmp_path, preview=True))
    held = S.held(tmp_path)
    assert len(held) == 3 and all("--linocut" in k for k in held), "the woodblock ones are gone"
    # settled twenty seconds on: they start
    seen = json.loads((tmp_path / "preview_seen.json").read_text())
    (tmp_path / "preview_seen.json").write_text(json.dumps({k: v - 30 for k, v in seen.items()}))
    cluster.fetch({**options, "style": "linocut"}, SETTINGS, ctx=_ctx(tmp_path, preview=True))
    _settle()
    assert len(prompts) == 3 and not S.held(tmp_path)
    assert all("linocut" in p["prompt"] for p in prompts)


def test_custom_builder_and_backdrop_prompts(tmp_path, offline):
    prompts, _ = offline
    plate.fetch({**MELBOURNE, "pictures": "paintings", "style": "custom", "custom_style": "a chalk pastel drawing on grey paper"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    assert "a chalk pastel drawing on grey paper" in prompts[-1]["prompt"]
    plate.fetch({**MELBOURNE, "pictures": "paintings", "style": "builder", "build_medium": "linocut", "build_period": "1930s", "build_palette": "duotone", "build_extra": "with gold on the tail"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    pr = prompts[-1]["prompt"]
    assert "a linocut print of the aircraft" in pr and "1930s travel poster" in pr and "two inks" in pr and "gold on the tail" in pr
    # a backdrop makes a whole picture, not a cut-out
    r = scene.fetch({**MELBOURNE, "pictures": "paintings", "style": "poster", "backdrop": "sunset"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    pr = prompts[-1]["prompt"]
    assert "sunset sky" in pr and "filling the frame" in pr and "contour line" not in pr and "pure white paper" not in pr
    r = scene.fetch({**MELBOURNE, "pictures": "paintings", "style": "poster", "backdrop": "sunset"}, SETTINGS, ctx=_ctx(tmp_path))
    a = r["aircraft"][0]
    assert a["pic"]["kind"] == "painting" and a["pic"]["whole"] is True and a["pic"]["src"].startswith("data:image/jpeg")
    assert P.key_for("VH-XVQ", "poster", "sunset") == "vh_xvq--poster--p1--bd_sunset"
    # the blueprint keeps its own paper
    scene.fetch({**MELBOURNE, "pictures": "paintings", "style": "blueprint", "backdrop": "sky"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    assert "Prussian blue" in prompts[-1]["prompt"]
    # a mono style asks for no colour
    plate.fetch({**MELBOURNE, "pictures": "paintings", "style": "engraving"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    assert "black, white and grey only" in prompts[-1]["prompt"]


def test_no_key_and_cap(tmp_path, offline):
    prompts, _ = offline
    r = cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "3"}, {"contact": "tester@example.com"}, ctx=_ctx(tmp_path))
    assert P.NOTE_NO_KEY in r["notices"] and not prompts
    assert all(a["pic"] and a["pic"]["kind"] == "photo" for a in r["aircraft"] if a["reg"] != "VH-NPS"), "the photograph shows meanwhile"
    r = cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "3"}, {**SETTINGS, "gen_daily_cap": "1"}, ctx=_ctx(tmp_path))
    _settle()
    assert len(prompts) == 1 and any("limit of 1" in s for s in r["status"])


def test_render_now_paints_only_what_the_panels_ask_for(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "count": "3"}
    cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert len(prompts) == 3
    gone = sorted((tmp_path / "gen").glob("*--poster--p1.jpg"))[0]
    gone.unlink()
    (gone.with_suffix(".json")).unlink()
    assert S.render_now(tmp_path, "k", 24) == (1, 1)
    _settle()
    assert len(prompts) == 4 and gone.exists()
    assert S.render_now(tmp_path, "k", 24) == (0, 0)


def test_core_gallery_and_purge(tmp_path, offline):
    cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "3"}, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    g = core.gallery(tmp_path, 24)
    assert len(g["paintings"]) == 3 and g["groups"][0]["name"] == "Hall" and g["groups"][0]["tabs"][0]["style_label"] == "Vintage airline poster"
    assert g["paintings"][0]["reg"] in ("B-LHP", "VH-VWN", "VH-XVQ", "VH-ZJS") and g["paintings"][0]["typ"]
    folder = tmp_path / "gen"
    P.archive(folder, g["paintings"][0]["key"])
    g = core.gallery(tmp_path, 24)
    assert any(e["archive"] for e in g["paintings"])
    got = core.purge_all(tmp_path)
    assert got == {"paintings": 2, "versions": 1}
    assert [f.name for f in folder.iterdir() if f.is_file()] == ["budget.json"]


def test_errors_are_words(tmp_path, offline):
    r = cluster.fetch({}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "error" and "Set a place" in r["error"]
    r = cluster.fetch({**MELBOURNE, "radius_km": "5", "include_ground": "false"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "ok" and [a["cs"] for a in r["aircraft"]] == ["QLK1997"]
    r = cluster.fetch({**MELBOURNE, "source": "receiver"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "error" and "receiver" in r["error"]


def test_lines_logos_and_panels(tmp_path, offline):
    r = cluster.fetch({**MELBOURNE, "labels": ["airline", "type", "reg", "route", "altitude", "distance", "speed", "heading"], "logos": "on", "panel": "mono", "count": "2"}, SETTINGS, ctx=_ctx(tmp_path))
    a = r["aircraft"][1]
    assert a["lines"][:4] == ["Rex", "Saab 340", "VH-ZJS", "Burnie to Melbourne"] and a["lines"][-1] == "heading 022°"
    assert a["logo"].startswith("data:image/png")
    raw = base64.b64decode(a["logo"].split(",", 1)[1])
    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    assert im.mode == "LA", "on a black-and-white panel the mark is ink and alpha only"
    assert a["pic"]["src"].startswith("data:image/jpeg")
