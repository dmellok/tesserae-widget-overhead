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

ROOT = Path(__file__).resolve().parents[2]


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
    {"hex": "780abc", "flight": "CRK035", "r": "B-LHP", "t": "A333", "alt_baro": 0, "gs": 120, "track": 352, "lat": -37.67, "lon": 144.843, "category": "A5"},
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
        if "open-meteo" in url:
            return json.dumps({"current": {"weather_code": 61, "cloud_cover": 90, "is_day": 1}, "daily": {"sunrise": ["2026-10-17T06:30"], "sunset": ["2026-10-17T19:40"]}}).encode(), None
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
        assert m["version"] == "0.1.8" and m["tesserae_compat"] == "1.x"
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
    assert next(r for r in rows if r["cs"] == "CRK035")["ground"] is True, "0 ft on a landing roll is the ground"
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
    assert "vintage mid-century airline poster" in p["prompt"] and "plain, pure white paper" in p["prompt"] and "unbroken dark contour line" in p["prompt"]
    assert "exactly as they are in the photograph" in p["prompt"] and "afresh" not in p["prompt"], "as photographed by default"
    assert r["status"] and "painting" in r["status"][0] and r["live_refresh_s"] > 0
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    painted = [a for a in r["aircraft"] if a["pic"] and a["pic"]["kind"] == "painting"]
    assert len(painted) == 3 and all(a["pic"]["src"].startswith("data:image/png") and not a["pic"]["whole"] for a in painted)
    gen = tmp_path / "gen"
    key = P.key_for("VH-XVQ", "poster")
    assert key == "vh_xvq--poster--p3" and (gen / f"{key}.jpg").exists() and (gen / f"{key}_cut{P.CUT_VERSION}.png").exists()
    meta = json.loads((gen / f"{key}.json").read_text())
    assert meta["reg"] == "VH-XVQ" and "A. Spotter" in meta["credit"]
    assert r["aircraft"][3]["pic"] is None and r["live_refresh_s"] == 0
    assert P.budget_used(gen) == 3
    # the dashboard's record for Render now
    d = S.dashboards(tmp_path)
    assert d and d[0]["name"] == "Hall" and len(d[0]["jobs"]) == 3
    # only painted aircraft: the Cessna goes
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
    assert P.key_for("VH-XVQ", "poster", "sunset") == "vh_xvq--poster--p3--bd_sunset"
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
    gone = sorted((tmp_path / "gen").glob("*--poster--p3.jpg"))[0]
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


def test_widgets_share_the_cores_folder(tmp_path, offline):
    mine = tmp_path / "overhead_cluster"
    mine.mkdir()
    cluster.fetch({**MELBOURNE, "count": "2"}, SETTINGS, ctx=_ctx(mine))
    assert (tmp_path / "overhead_core" / "live").exists() and not (mine / "live").exists()


def test_a_private_aircraft_has_no_operator_in_its_record(tmp_path, offline):
    prompts, _ = offline
    # the Cessna has no photo, so give one to a private registration: VH-AL2 style callsign
    AC.append({"hex": "7c1234", "flight": "VH-ABC", "r": "VH-ABC", "t": "C182", "alt_baro": 2000, "gs": 100, "track": 10, "lat": -37.671, "lon": 144.841, "category": "A1"})
    try:
        cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "1", "radius_km": "5"}, SETTINGS, ctx=_ctx(tmp_path))
        _settle()
    finally:
        AC.pop()
    pr = prompts[-1]["prompt"]
    assert "VH-ABC in its own livery" in pr and "private" not in pr
    meta = json.loads(next((tmp_path / "gen").glob("vh_abc--*.json")).read_text())
    assert meta["air"] == ""


def test_only_painted_aircraft(tmp_path, offline):
    prompts, _ = offline
    # nothing painted yet: the page says so and paints
    r = cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "3", "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "painting" and "Painting 3" in r["hint"] and r["live_refresh_s"] > 0 and r["aircraft"] == []
    _settle()
    r = cluster.fetch({**MELBOURNE, "pictures": "paintings", "count": "3", "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "ok" and len(r["aircraft"]) == 3 and all(a["pic"]["kind"] == "painting" for a in r["aircraft"])
    # a single page: the nearest painted among the nearest few, the rest painted meanwhile
    (tmp_path / "gen" / P.key_for("VH-XVQ", "poster")).with_suffix(".jpg").unlink()
    r = plate.fetch({**MELBOURNE, "pictures": "paintings", "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "ok" and r["aircraft"][0]["cs"] == "RXA3558", "the nearest is being painted again; the next painted one shows"
    assert any(s.startswith("painting 3 of 4") for s in r["status"]), "counted over the pool, not the one shown"
    _settle()
    r = plate.fetch({**MELBOURNE, "pictures": "paintings", "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["aircraft"][0]["cs"] == "QLK1997"
    # without a key, the photograph does not stand in: the page says what it waits for
    (tmp_path / "gen" / P.key_for("VH-XVQ", "poster")).with_suffix(".jpg").unlink()
    r = scene.fetch({**MELBOURNE, "pictures": "paintings", "unpainted": "skip", "radius_km": "5"}, {"contact": "tester@example.com"}, ctx=_ctx(tmp_path))
    assert r["state"] == "painting" and P.NOTE_NO_KEY in r["hint"]


def test_the_cut_out_keeps_a_white_fuselage_inside_its_outline():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((100, 150, 500, 250), outline=(30, 30, 30), width=3, fill=(255, 255, 255))  # a white fuselage with a contour
    d.rectangle((280, 100, 320, 150), fill=(200, 30, 30))  # a red tail
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    assert png
    cut = Image.open(io.BytesIO(png)).convert("RGBA")
    a = cut.split()[3]
    assert a.getpixel((cut.width // 2, cut.height - 50)) > 200, "white paint inside the outline stays"
    assert a.getpixel((2, 2)) < 20, "paper outside the outline goes"


def test_the_cut_out_steps_inside_a_drawn_frame():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((6, 6, 593, 393), outline=(40, 40, 40), width=4)  # a frame the model drew round the page
    d.ellipse((150, 150, 450, 250), fill=(180, 40, 40))  # the aircraft
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    assert png
    cut = Image.open(io.BytesIO(png))
    assert cut.width < 340 and cut.height < 130, "the page inside the frame is let go; the cut is the aircraft alone"


def test_font_and_scale_are_echoed(tmp_path, offline):
    r = cluster.fetch({**MELBOURNE, "font": "archivo", "scale": "70", "count": "2"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["font"] == "archivo" and r["scale"] == 70
    r = cluster.fetch({**MELBOURNE, "font": "comic", "scale": "900", "count": "2"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["font"] == "fell" and r["scale"] == 100


def test_the_sky_as_it_is_now(tmp_path, offline):
    prompts, _ = offline
    assert A.weather_bucket(61, 90) == "rain" and A.weather_bucket(0, 10) == "clear" and A.weather_bucket(2, 40) == "partly" and A.weather_bucket(95, 100) == "storm"
    assert A.time_bucket(6 * 60 + 40, 6 * 60 + 30, 19 * 60 + 40) == "dawn" and A.time_bucket(12 * 60, 390, 1180) == "midday" and A.time_bucket(22 * 60, 390, 1180) == "night" and A.time_bucket(19 * 60 + 20, 390, 1180) == "dusk"
    tod, wx = A.sky_now(-37.67, 144.84, 9 * 60, tmp_path, "ua")
    assert (tod, wx) == ("morning", "rain")
    r = scene.fetch({**MELBOURNE, "pictures": "paintings", "backdrop": "live"}, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    pr = prompts[-1]["prompt"]
    assert "rain clouds" in pr and "filling the frame" in pr and r["sky"]["weather"] == "rain"
    key = next((tmp_path / "gen").glob("*--bd_*.jpg")).stem
    assert key.endswith("_rain") and "bd_" in key


def test_the_cut_out_drops_a_darker_rim_and_specks():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 599, 399), outline=(228, 228, 228), width=2)  # a faintly darker rim the model left at the edge
    d.ellipse((150, 150, 450, 250), fill=(180, 40, 40))
    d.ellipse((520, 60, 526, 66), fill=(40, 40, 40))  # a speck
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    cut = Image.open(io.BytesIO(png))
    assert cut.width < 320 and cut.height < 120, f"the rim and the speck are gone, the cut is the aircraft alone: {cut.size}"


def test_every_style_is_offered_and_prompts():
    m = json.loads((ROOT / "overhead_cluster" / "plugin.json").read_text(encoding="utf-8"))
    offered = [c["value"] for c in next(o for o in m["cell_options"] if o["name"] == "style")["choices"]]
    assert offered == [*P.STYLES, "builder", "custom"] and len(P.STYLES) >= 26
    for sid, (label, how) in P.STYLES.items():
        pr = P.prompt_for({"key": "x", "reg": "VH-ABC", "typ": "Boeing 737-800", "air": "Qantas", "style": sid, "backdrop": "none", "view": "side", "fidelity": "free"})
        assert how.split(":")[0] in pr and label
        assert ("pure white paper" in pr) == (sid not in P.OWN_PAPER)


def test_the_livery_view_and_the_reference_link(tmp_path, offline):
    prompts, _ = offline
    plate.fetch({**MELBOURNE, "pictures": "paintings", "view": "livery", "fidelity": "free"}, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert "pure profile view" in prompts[-1]["prompt"] and "afresh" in prompts[-1]["prompt"]
    key = next((tmp_path / "gen").glob("*--v_livery.jpg")).stem
    assert key.endswith("--free--v_livery")
    plate.fetch({**MELBOURNE, "pictures": "paintings", "view": "livery"}, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert "pure profile" not in prompts[-1]["prompt"], "as photographed: the view is the photograph's"
    g = core.gallery(tmp_path, 24)
    e = g["paintings"][0]
    assert e["photo_link"].startswith("https://www.planespotters.net/photo/") and e["photo_by"] == "A. Spotter"


def test_a_refused_prompt_is_asked_once_more(tmp_path, offline, monkeypatch):
    calls = []
    real = N.http

    def flaky(url, token="", accept="application/json", **kw):
        if "fal.run" in url:
            calls.append(1)
            if len(calls) == 1:
                return None, "HTTP 422: The model did not generate the expected output"
        return real(url, token, accept, **kw)

    monkeypatch.setattr(N, "http", flaky)
    why = P.paint({"key": "k1", "reg": "VH-ABC", "typ": "Boeing 737-800", "air": "Qantas", "style": "poster", "photo": "https://t.example/VH-ABC.jpg"}, tmp_path, "k")
    assert why is None and len(calls) == 2 and (tmp_path / "gen" / "k1.jpg").exists()

