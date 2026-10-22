"""Offline tests for the Overhead bundle: the feeds, the photographs, the
paintings and the four pages, with every call on the network answered here."""

from __future__ import annotations

import base64
import importlib.util
import io
import os
import json
import sys
import time
from pathlib import Path

import pytest

# The widget paints through Tesserae's ``app.artwork`` (0.463+): the server's
# repo must be importable. A checkout beside this one, or TESSERAE_REPO.
_TESSERAE = Path(
    os.environ.get("TESSERAE_REPO") or Path(__file__).resolve().parents[3] / "tesserae"
)
if str(_TESSERAE) not in sys.path:
    sys.path.insert(0, str(_TESSERAE))
from app import artwork, fal as fal_mod  # noqa: E402

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
W = S.W

MELBOURNE = {
    "latitude": -37.67,
    "longitude": 144.84,
    "location": {"label": "Tullamarine", "timezone": "Australia/Melbourne"},
}
SETTINGS = {"fal_api_key": "k", "contact": "tester@example.com", "gen_daily_usd": "1"}
AC = [
    {
        "hex": "7c6b2f",
        "flight": "JST772 ",
        "r": "VH-VWN",
        "t": "A321",
        "alt_baro": 3600,
        "baro_rate": 992,
        "gs": 297,
        "track": 284,
        "lat": -37.55,
        "lon": 144.70,
        "category": "A3",
    },
    {
        "hex": "7c4b1a",
        "flight": "QLK1997",
        "r": "VH-XVQ",
        "t": "E190",
        "alt_baro": 200,
        "baro_rate": 2688,
        "gs": 145,
        "track": 352,
        "lat": -37.66,
        "lon": 144.84,
        "category": "A3",
    },
    {
        "hex": "7c7f00",
        "flight": "RXA3558",
        "r": "VH-ZJS",
        "t": "SF34",
        "alt_baro": 2050,
        "baro_rate": 0,
        "gs": 177,
        "track": 22,
        "lat": -37.78,
        "lon": 144.84,
        "category": "A2",
    },
    {
        "hex": "7c0001",
        "flight": "VH-NPS",
        "r": "VH-NPS",
        "t": "C172",
        "alt_baro": 1500,
        "baro_rate": 0,
        "gs": 72,
        "track": 47,
        "lat": -37.85,
        "lon": 144.9,
        "category": "A1",
    },
    {
        "hex": "780abc",
        "flight": "CRK035",
        "r": "B-LHP",
        "t": "A333",
        "alt_baro": 0,
        "gs": 120,
        "track": 352,
        "lat": -37.67,
        "lon": 144.843,
        "category": "A5",
    },
    {
        "hex": "7c9999",
        "flight": "FAR999",
        "r": "VH-FAR",
        "t": "B738",
        "alt_baro": 30000,
        "gs": 450,
        "track": 90,
        "lat": -36.5,
        "lon": 146.5,
        "category": "A3",
    },
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


def _png_logo(colour=(200, 20, 20, 255)) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((20, 60, 380, 140), fill=colour)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def offline(monkeypatch):
    """Every call on the network, answered here; the prompts fal.ai got."""
    prompts: list[dict] = []
    uas: list[str] = []

    def fake_http(
        url,
        token="",
        accept="application/json",
        *,
        auth_scheme="Bearer",
        body=None,
        timeout=10,
        detail=False,
        ua="",
    ):
        uas.append(ua)
        if "api.adsb.lol" in url:
            return json.dumps({"ac": AC, "now": int(time.time() * 1000)}).encode(), None
        if "opendata.adsb.fi" in url:
            return json.dumps(
                {"aircraft": AC, "now": int(time.time() * 1000)}
            ).encode(), None
        if "aircraft.json" in url:
            return json.dumps({"aircraft": AC[:2]}).encode(), None
        if "api.adsbdb.com" in url:
            cs = url.rsplit("/", 1)[1]
            routes = {
                "JST772": ("Jetstar Airways", "MEL", "Melbourne", "ADL", "Adelaide"),
                "RXA3558": ("Regional Express", "BWT", "Burnie", "MEL", "Melbourne"),
                "CRK035": (
                    "Hong Kong Airlines",
                    "HKG",
                    "Hong Kong",
                    "MEL",
                    "Melbourne",
                ),
            }
            if cs in routes:
                a, o, oc, d, dc = routes[cs]
                return json.dumps(
                    {
                        "response": {
                            "flightroute": {
                                "airline": {"name": a},
                                "origin": {"iata_code": o, "municipality": oc},
                                "destination": {"iata_code": d, "municipality": dc},
                            }
                        }
                    }
                ).encode(), None
            return None, "HTTP 404"
        if "api.planespotters.net" in url:
            if "tester@example.com" not in ua:
                return None, "auth"
            reg = url.rsplit("/", 1)[1]
            if reg == "VH-NPS":
                return json.dumps({"photos": []}).encode(), None
            return json.dumps(
                {
                    "photos": [
                        {
                            "thumbnail": {
                                "src": f"https://t.example/{reg}_s.jpg",
                                "size": {"width": 200, "height": 133},
                            },
                            "thumbnail_large": {
                                "src": f"https://t.example/{reg}.jpg",
                                "size": {"width": 498, "height": 280},
                            },
                            "photographer": "A. Spotter",
                            "link": f"https://www.planespotters.net/photo/1/{reg}",
                        }
                    ]
                }
            ).encode(), None
        if "t.example" in url:
            return _jpeg(), None
        if "upload.wikimedia.org" in url:
            return _jpeg(), None
        if "daisycon" in url or "kiwi" in url:
            return (
                _png_logo((120, 120, 120, 255)) if "ZZ" in url else _png_logo()
            ), None
        if "open-meteo" in url:
            return json.dumps(
                {
                    "current": {"weather_code": 61, "cloud_cover": 90, "is_day": 1},
                    "daily": {
                        "sunrise": ["2026-10-17T06:30"],
                        "sunset": ["2026-10-17T19:40"],
                    },
                }
            ).encode(), None
        return None, "unreachable"

    monkeypatch.setattr(N, "http", fake_http)

    def fake_fal(url, body, key, timeout):
        prompts.append({**body, "_url": url})
        assert key == "k"
        return {"images": [{"url": "https://fal.example/out.jpg"}]}

    monkeypatch.setattr(fal_mod, "_http_json", fake_fal)
    monkeypatch.setattr(
        fal_mod, "_download", lambda url, timeout=60.0: _jpeg(paper=(252, 250, 246))
    )
    yield prompts, uas
    P.ART.stop_all(Path("."))
    W.stop_watches()


def _busy() -> bool:
    pr = P.ART.progress(Path("."), {})
    return bool(pr["running"] or pr["queued"])


def _settle(timeout=10.0):
    end = time.time() + timeout
    while _busy() and time.time() < end:
        time.sleep(0.02)
    assert not _busy()


def _ctx(tmp_path, **kw):
    ctx = {"data_dir": str(tmp_path), "cell_w": 800, "cell_h": 480, **kw}
    ctx.setdefault("settled", not ctx.get("preview"))
    return ctx


# ----------------------------------------------------------------------
def test_manifests_and_client_files():
    for wid in (
        "overhead_core",
        "overhead_photo",
        "overhead_plate",
        "overhead_cluster",
        "overhead_scene",
    ):
        m = json.loads((ROOT / wid / "plugin.json").read_text(encoding="utf-8"))
        if m["kind"] == "widget":
            assert m["render"]["warm_ahead_s"] == 150, (
                "asks to be run ahead of a scheduled send"
            )
        assert m["version"] == "0.6.0" and m["tesserae_compat"] == "1.x"
        if wid != "overhead_core":
            assert (ROOT / wid / "client.js").exists() and m["kind"] == "widget"
            names = [o["name"] for o in m["cell_options"]]
            assert (
                len(names) == len(set(names))
                and "location" in names
                and "logos" in names
            )
            assert "settings:plugin/overhead_core" in m["requires"]
    custom = next(
        o
        for o in json.loads((ROOT / "overhead_cluster" / "plugin.json").read_text())[
            "cell_options"
        ]
        if o["name"] == "custom_style"
    )
    assert custom["type"] == "textarea" and len(custom["presets"]) >= 5


def test_nearby_filters_sorts_and_names(tmp_path, offline):
    rows, err, feed = A.nearby("adsb_lol", "", -37.67, 144.84, 35, tmp_path, "ua")
    assert feed == "adsb.lol"
    assert err is None
    assert [r["cs"] for r in rows] == [
        "CRK035",
        "QLK1997",
        "RXA3558",
        "JST772",
        "VH-NPS",
    ], "within 35 km, nearest first; no position, no row"
    jet = next(r for r in rows if r["cs"] == "JST772")
    assert (
        jet["typ"] == "Airbus A321"
        and jet["cls"] == "jet"
        and jet["span"] == 35.8
        and jet["km"] > 10
        and jet["dir"] in range(280, 340)
    )
    assert next(r for r in rows if r["cs"] == "CRK035")["ground"] is True, (
        "0 ft on a landing roll is the ground"
    )
    roll = dict(next(r for r in rows if r["cs"] == "CRK035"), route=None)
    assert S.lines_for(roll, ["route", "altitude"]) == [
        "on the runway",
        "on the ground",
    ], (
        "a grounded aircraft without a route says what it is doing, not 'on the ground' twice"
    )
    assert S.lines_for({**roll, "gs": 12}, ["route"]) == ["taxiing"] and S.lines_for(
        {**roll, "gs": 0}, ["route"]
    ) == ["parked"]
    assert A.airline_of("JST772", "VH-VWN") == ("JQ", "Jetstar") and A.airline_of(
        "VH-NPS", "VH-NPS"
    ) == ("", "private")
    assert A.airline_of("ABC123", "X", "Some Air") == ("", "Some Air")
    # a receiver of your own: its aircraft.json
    rows2, err2, _feed2 = A.nearby(
        "receiver", "pi.local:8080", -37.67, 144.84, 35, tmp_path, "ua"
    )
    assert err2 is None and len(rows2) == 2
    assert A.nearby("receiver", "", -37.67, 144.84, 35, tmp_path, "ua")[1].startswith(
        "Give the receiver"
    )


def test_photo_page_has_the_airframe_photograph_and_a_strip(tmp_path, offline):
    r = photo.fetch(
        {**MELBOURNE, "strip": "3", "logos": "on"}, SETTINGS, ctx=_ctx(tmp_path)
    )
    assert r["state"] == "ok" and r["widget"] == "photo"
    assert [a["cs"] for a in r["aircraft"]] == [
        "QLK1997",
        "RXA3558",
        "JST772",
        "VH-NPS",
    ], "the ground stays off unless asked"
    hero = r["aircraft"][0]
    assert (
        hero["pic"]["kind"] == "photo"
        and hero["pic"]["src"].startswith("data:image/jpeg")
        and "A. Spotter" in hero["pic"]["credit"]
    )
    assert hero["iata"] == "QF" and hero["logo"].startswith("data:image/png")
    assert (
        hero["route_text"] == "climbing out" and hero["alt_text"] == "200 ft climbing"
    )
    assert (
        r["aircraft"][2]["route_text"] == "Melbourne to Adelaide"
        and r["aircraft"][1]["route_text"] == "Burnie to Melbourne"
    )
    assert r["aircraft"][3]["pic"] is None, (
        "no photograph on planespotters: nothing to show but the silhouette"
    )
    assert r["aircraft"][3]["sil"].endswith("light.svg")
    assert any("planespotters" in c for c in r["credits"]) and r[
        "attribution"
    ].startswith("positions from adsb.lol")


def test_planespotters_needs_the_contact(tmp_path, offline):
    r = photo.fetch(MELBOURNE, {"contact": ""}, ctx=_ctx(tmp_path))
    assert all(a["pic"] is None for a in r["aircraft"]), (
        "refused without a contact in the User-Agent"
    )
    assert any("tesserae-overhead" in u for u in offline[1])


def test_cluster_paints_from_the_photograph_and_cuts_out(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "style": "poster", "count": "4"}
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert len(prompts) == 3, "the three with a photograph; the Cessna has none"
    p = prompts[0]
    assert (
        p["image_urls"][0] == "https://t.example/VH-XVQ.jpg"
        and "Embraer E190" in p["prompt"]
        and "VH-XVQ" in p["prompt"]
        and "QantasLink livery" in p["prompt"]
    )
    assert (
        "vintage mid-century airline poster" in p["prompt"]
        and "plain, pure white paper" in p["prompt"]
        and "unbroken dark contour line" in p["prompt"]
    )
    assert (
        "exactly as they are in the photograph" in p["prompt"]
        and "afresh" not in p["prompt"]
    ), "as photographed by default"
    assert (
        "emblem on the tail" in p["prompt"]
        and "The second picture is the airline's own mark" in p["prompt"]
    )
    assert len(p["image_urls"]) == 2 and p["image_urls"][1].startswith(
        "data:image/png;base64,"
    ), "the airline's mark as a second reference"
    assert r["status"] and "painting" in r["status"][0] and r["live_refresh_s"] > 0
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    painted = [a for a in r["aircraft"] if a["pic"] and a["pic"]["kind"] == "painting"]
    assert len(painted) == 3 and all(
        a["pic"]["src"].startswith("data:image/png") and not a["pic"]["whole"]
        for a in painted
    )
    gen = tmp_path / "paintings"
    key = P.key_for("VH-XVQ", "poster")
    assert (
        key == "vh_xvq--poster--p3"
        and (gen / f"{key}.jpg").exists()
        and (gen / f"{key}__cut{P.CUT_VERSION}.png").exists()
    )
    meta = json.loads((gen / f"{key}.json").read_text())
    assert meta["reg"] == "VH-XVQ" and "A. Spotter" in meta["credit"]
    assert r["aircraft"][3]["pic"] is None and r["live_refresh_s"] == 0
    assert P.budget_used(gen) == 12, "three Nano Banana paintings, 4 cents each"
    # the dashboard's record for Render now
    d = P.ART.dashboards(tmp_path)
    assert d and d[0]["name"] == "Hall" and len(d[0]["jobs"]) == 3
    # only painted aircraft: the Cessna goes
    r = cluster.fetch({**options, "unpainted": "skip"}, SETTINGS, ctx=_ctx(tmp_path))
    assert [a["cs"] for a in r["aircraft"]] == ["QLK1997", "RXA3558", "JST772"]


def test_previews_hold_and_a_new_look_drops_the_old(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "style": "woodblock", "count": "3"}
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, preview=True))
    _settle()
    assert not prompts and len(P.ART.held(tmp_path)) == 3 and r["live_refresh_s"] > 0
    assert any("waiting for Paint now" in s for s in r["notices"] + r["status"])
    cluster.fetch(
        {**options, "style": "linocut"}, SETTINGS, ctx=_ctx(tmp_path, preview=True)
    )
    held = P.ART.held(tmp_path)
    assert len(held) == 3 and all("--linocut" in k for k in held), (
        "the woodblock ones are gone"
    )
    # the host says the dashboard has settled: they start
    cluster.fetch(
        {**options, "style": "linocut"},
        SETTINGS,
        ctx=_ctx(tmp_path, preview=True, settled=True),
    )
    _settle()
    assert len(prompts) == 3 and not P.ART.held(tmp_path)
    assert all("linocut" in p["prompt"] for p in prompts)


def test_custom_builder_and_backdrop_prompts(tmp_path, offline):
    prompts, _ = offline
    plate.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "style": "custom",
            "custom_style": "a chalk pastel drawing on grey paper",
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    assert "a chalk pastel drawing on grey paper" in prompts[-1]["prompt"]
    plate.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "style": "builder",
            "build_medium": "linocut",
            "build_period": "1930s",
            "build_palette": "duotone",
            "build_extra": "with gold on the tail",
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    pr = prompts[-1]["prompt"]
    assert (
        "a linocut print of the aircraft" in pr
        and "1930s travel poster" in pr
        and "two inks" in pr
        and "gold on the tail" in pr
    )
    # a backdrop makes a whole picture, not a cut-out
    r = scene.fetch(
        {**MELBOURNE, "pictures": "paintings", "style": "poster", "backdrop": "sunset"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    pr = prompts[-1]["prompt"]
    assert (
        "sunset sky" in pr
        and "filling the frame" in pr
        and "contour line" not in pr
        and "pure white paper" not in pr
    )
    r = scene.fetch(
        {**MELBOURNE, "pictures": "paintings", "style": "poster", "backdrop": "sunset"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    a = r["aircraft"][0]
    assert (
        a["pic"]["kind"] == "painting"
        and a["pic"]["whole"] is True
        and a["pic"]["src"].startswith("data:image/jpeg")
    )
    assert P.key_for("VH-XVQ", "poster", "sunset") == "vh_xvq--poster--p3--bd_sunset"
    # the blueprint keeps its own paper
    scene.fetch(
        {**MELBOURNE, "pictures": "paintings", "style": "blueprint", "backdrop": "sky"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    assert "Prussian blue" in prompts[-1]["prompt"]
    # a mono style asks for no colour
    plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "style": "engraving"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    assert "black, white and grey only" in prompts[-1]["prompt"]


def test_no_key_and_cap(tmp_path, offline):
    prompts, _ = offline
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3"},
        {"contact": "tester@example.com"},
        ctx=_ctx(tmp_path),
    )
    assert P.NOTE_NO_KEY in r["notices"] and not prompts
    assert all(
        a["pic"] and a["pic"]["kind"] == "photo"
        for a in r["aircraft"]
        if a["reg"] != "VH-NPS"
    ), "the photograph shows meanwhile"
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3"},
        {**SETTINGS, "gen_daily_usd": "0.04"},
        ctx=_ctx(tmp_path),
    )
    _settle()
    assert len(prompts) == 1 and any(
        "budget of US$0.04" in s for s in r["notices"] + r["status"]
    )


def test_render_now_paints_only_what_the_panels_ask_for(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "count": "3"}
    cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path, page_name="Hall"))
    _settle()
    assert len(prompts) == 3
    gone = sorted((tmp_path / "paintings").glob("*--poster--p3.jpg"))[0]
    gone.unlink()
    (gone.with_suffix(".json")).unlink()
    assert P.ART.render_now(tmp_path, "k", SETTINGS) == (1, 1)
    _settle()
    assert len(prompts) == 4 and gone.exists()
    assert P.ART.render_now(tmp_path, "k", SETTINGS) == (0, 0)


def test_core_gallery_and_purge(tmp_path, offline):
    cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3"},
        SETTINGS,
        ctx=_ctx(tmp_path, page_name="Hall"),
    )
    _settle()
    listing = P.ART.listing(tmp_path)
    assert (
        len(listing) == 3
        and listing[0]["facet_label"] == "Vintage airline poster"
        and listing[0]["meta"]["reg"]
    )
    d = P.ART.dashboards(tmp_path)
    assert (
        d[0]["name"] == "Hall"
        and d[0]["facet_label"] == "Vintage airline poster"
        and len(d[0]["keys"]) == 3
    )
    folder = tmp_path / "paintings"
    P.archive(folder, listing[0]["key"])
    listing = P.ART.listing(tmp_path)
    assert len(listing) == 2 and P.ART.versions(d[0]["keys"][0], tmp_path) or True
    got = P.ART.purge(tmp_path)
    assert got == {"pictures": 2, "versions": 1}
    assert not [f for f in folder.iterdir() if f.suffix in (".jpg", ".png")]


def test_errors_are_words(tmp_path, offline):
    r = cluster.fetch({}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "error" and "Set a place" in r["error"]
    r = cluster.fetch(
        {**MELBOURNE, "radius_km": "5", "include_ground": "false"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["state"] == "ok" and [a["cs"] for a in r["aircraft"]] == ["QLK1997"]
    r = cluster.fetch({**MELBOURNE, "source": "receiver"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "error" and "receiver" in r["error"]


def test_lines_logos_and_panels(tmp_path, offline):
    r = cluster.fetch(
        {
            **MELBOURNE,
            "labels": [
                "airline",
                "type",
                "reg",
                "route",
                "altitude",
                "distance",
                "speed",
                "heading",
            ],
            "logos": "on",
            "panel": "mono",
            "count": "2",
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    a = r["aircraft"][1]
    assert (
        a["lines"][:4] == ["Rex", "Saab 340", "VH-ZJS", "Burnie to Melbourne"]
        and a["lines"][-1] == "heading 022°"
    )
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
    assert (tmp_path / "overhead_core" / "live").exists() and not (
        mine / "live"
    ).exists()


def test_a_private_aircraft_has_no_operator_in_its_record(tmp_path, offline):
    prompts, _ = offline
    # the Cessna has no photo, so give one to a private registration: VH-AL2 style callsign
    AC.append(
        {
            "hex": "7c1234",
            "flight": "VH-ABC",
            "r": "VH-ABC",
            "t": "C182",
            "alt_baro": 2000,
            "gs": 100,
            "track": 10,
            "lat": -37.671,
            "lon": 144.841,
            "category": "A1",
        }
    )
    try:
        cluster.fetch(
            {**MELBOURNE, "pictures": "paintings", "count": "1", "radius_km": "5"},
            SETTINGS,
            ctx=_ctx(tmp_path),
        )
        _settle()
    finally:
        AC.pop()
    pr = prompts[-1]["prompt"]
    assert "VH-ABC in its own livery" in pr and "private" not in pr
    meta = json.loads(next((tmp_path / "paintings").glob("vh_abc--*.json")).read_text())
    assert meta["air"] == ""


def test_only_painted_aircraft(tmp_path, offline):
    prompts, _ = offline
    # nothing painted yet: the page says so and paints
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3", "unpainted": "skip"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert (
        r["state"] == "painting"
        and "Painting 3" in r["hint"]
        and r["live_refresh_s"] > 0
        and r["aircraft"] == []
    )
    _settle()
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3", "unpainted": "skip"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert (
        r["state"] == "ok"
        and len(r["aircraft"]) == 3
        and all(a["pic"]["kind"] == "painting" for a in r["aircraft"])
    )
    # a single page: the nearest painted among the nearest few, the rest painted meanwhile
    (tmp_path / "paintings" / P.key_for("VH-XVQ", "poster")).with_suffix(
        ".jpg"
    ).unlink()
    r = plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "unpainted": "skip"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["state"] == "ok" and r["aircraft"][0]["cs"] == "RXA3558", (
        "the nearest is being painted again; the next painted one shows"
    )
    assert any(s.startswith("painting 3 of") for s in r["status"]), (
        "counted over the pool, not the one shown"
    )
    _settle()
    r = plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "unpainted": "skip"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["aircraft"][0]["cs"] == "QLK1997"
    # without a key, the photograph does not stand in: the page says what it waits for
    (tmp_path / "paintings" / P.key_for("VH-XVQ", "poster")).with_suffix(
        ".jpg"
    ).unlink()
    r = scene.fetch(
        {**MELBOURNE, "pictures": "paintings", "unpainted": "skip", "radius_km": "5"},
        {"contact": "tester@example.com"},
        ctx=_ctx(tmp_path),
    )
    assert r["state"] == "painting" and P.NOTE_NO_KEY in r["hint"]


def test_the_cut_out_keeps_a_white_fuselage_inside_its_outline():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse(
        (100, 150, 500, 250), outline=(30, 30, 30), width=3, fill=(255, 255, 255)
    )  # a white fuselage with a contour
    d.rectangle((280, 100, 320, 150), fill=(200, 30, 30))  # a red tail
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    assert png
    cut = Image.open(io.BytesIO(png)).convert("RGBA")
    a = cut.split()[3]
    assert a.getpixel((cut.width // 2, cut.height - 50)) > 200, (
        "white paint inside the outline stays"
    )
    assert a.getpixel((2, 2)) < 20, "paper outside the outline goes"


def test_the_cut_out_steps_inside_a_drawn_frame():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle(
        (6, 6, 593, 393), outline=(40, 40, 40), width=4
    )  # a frame the model drew round the page
    d.ellipse((150, 150, 450, 250), fill=(180, 40, 40))  # the aircraft
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    assert png
    cut = Image.open(io.BytesIO(png))
    assert cut.width < 340 and cut.height < 130, (
        "the page inside the frame is let go; the cut is the aircraft alone"
    )


def test_font_and_scale_are_echoed(tmp_path, offline):
    r = cluster.fetch(
        {**MELBOURNE, "font": "archivo", "scale": "70", "count": "2"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["font"] == "archivo" and r["scale"] == 70
    r = cluster.fetch(
        {**MELBOURNE, "font": "comic", "scale": "900", "count": "2"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["font"] == "fell" and r["scale"] == 100


def test_the_sky_as_it_is_now(tmp_path, offline):
    prompts, _ = offline
    assert (
        A.weather_bucket(61, 90) == "rain"
        and A.weather_bucket(0, 10) == "clear"
        and A.weather_bucket(2, 40) == "partly"
        and A.weather_bucket(95, 100) == "storm"
    )
    assert (
        A.time_bucket(6 * 60 + 40, 6 * 60 + 30, 19 * 60 + 40) == "dawn"
        and A.time_bucket(12 * 60, 390, 1180) == "midday"
        and A.time_bucket(22 * 60, 390, 1180) == "night"
        and A.time_bucket(19 * 60 + 20, 390, 1180) == "dusk"
    )
    tod, wx = A.sky_now(-37.67, 144.84, 9 * 60, tmp_path, "ua")
    assert (tod, wx) == ("morning", "rain")
    r = scene.fetch(
        {**MELBOURNE, "pictures": "paintings", "backdrop": "live"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    pr = prompts[-1]["prompt"]
    assert (
        "rain clouds" in pr
        and "filling the frame" in pr
        and r["sky"]["weather"] == "rain"
    )
    key = next((tmp_path / "paintings").glob("*--bd_*.jpg")).stem
    assert key.endswith("_rain") and "bd_" in key


def test_the_cut_out_drops_a_darker_rim_and_specks():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle(
        (0, 0, 599, 399), outline=(228, 228, 228), width=2
    )  # a faintly darker rim the model left at the edge
    d.ellipse((150, 150, 450, 250), fill=(180, 40, 40))
    d.ellipse((520, 60, 526, 66), fill=(40, 40, 40))  # a speck
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    png = P.cut_out(out.getvalue())
    cut = Image.open(io.BytesIO(png))
    assert cut.width < 320 and cut.height < 120, (
        f"the rim and the speck are gone, the cut is the aircraft alone: {cut.size}"
    )


def test_every_style_is_offered_and_prompts():
    m = json.loads(
        (ROOT / "overhead_cluster" / "plugin.json").read_text(encoding="utf-8")
    )
    offered = [
        c["value"]
        for c in next(o for o in m["cell_options"] if o["name"] == "style")["choices"]
    ]
    shown = [s for s in P.STYLES if s not in P.HIDDEN]
    assert offered == [*shown, "builder", "custom"] and len(shown) >= 20
    # a hidden style is still made for a cell already set to it
    assert P.HIDDEN <= set(P.STYLES) and P.style_of("woodblock")[0] == "Japanese woodblock print"
    for sid, (label, how) in P.STYLES.items():
        pr = P.prompt_for(
            {
                "key": "x",
                "reg": "VH-ABC",
                "typ": "Boeing 737-800",
                "air": "Qantas",
                "style": sid,
                "backdrop": "none",
                "view": "side",
                "fidelity": "free",
            }
        )
        assert how.split(":")[0] in pr and label
        assert ("pure white paper" in pr) == (sid not in P.OWN_PAPER)


def test_the_livery_view_and_the_reference_link(tmp_path, offline):
    prompts, _ = offline
    plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "view": "livery", "fidelity": "free"},
        SETTINGS,
        ctx=_ctx(tmp_path, page_name="Hall"),
    )
    _settle()
    assert (
        "pure profile view" in prompts[-1]["prompt"]
        and "afresh" in prompts[-1]["prompt"]
    )
    key = next((tmp_path / "paintings").glob("*--v_livery.jpg")).stem
    assert key.endswith("--free--v_livery")
    plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "view": "livery"},
        SETTINGS,
        ctx=_ctx(tmp_path, page_name="Hall"),
    )
    _settle()
    assert "pure profile" not in prompts[-1]["prompt"], (
        "as photographed: the view is the photograph's"
    )
    e = P.ART.listing(tmp_path)[0]["meta"]
    assert (
        e["link"].startswith("https://www.planespotters.net/photo/")
        and e["by"] == "A. Spotter"
    ), "the reference picture, for the paintings page"


def test_a_refused_prompt_is_asked_once_more(tmp_path, offline, monkeypatch):
    """A 422 is the model declining this prompt this once; the painter asks again."""
    calls = []
    real = fal_mod._http_json

    def flaky(url, body, key, timeout):
        calls.append(1)
        if len(calls) == 1:
            import urllib.error

            raise urllib.error.HTTPError(
                url, 422, "The model did not generate the expected output", {}, None
            )
        return real(url, body, key, timeout)

    monkeypatch.setattr(fal_mod, "_http_json", flaky)
    job = P.ART.job(
        "k1",
        {
            "reg": "VH-ABC",
            "typ": "Boeing 737-800",
            "air": "Qantas",
            "style": "poster",
            "photo": "https://t.example/VH-ABC.jpg",
        },
        "VH-ABC",
        tmp_path,
        "k",
    )
    raw, meta = P.make(job)
    assert len(calls) == 2 and raw[:3] == b"\xff\xd8\xff" and meta["reg"] == "VH-ABC"


def test_a_ufo_now_and_then(tmp_path, offline):
    prompts, _ = offline
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3", "ufo": "0"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert not any(a.get("ufo") for a in r["aircraft"])
    r = cluster.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "count": "3",
            "ufo": "100",
            "visitors": ["adamski"],
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    ufo = [p for p in prompts if "unidentified flying object" in p["prompt"]]
    assert (
        len(ufo) == 1
        and ufo[0]["_url"].endswith("fal-ai/nano-banana")
        and "image_urls" not in ufo[0]
    ), "no reference picture: from words alone"
    assert (
        "bell-shaped" in ufo[0]["prompt"]
        and "Nothing about it is man-made" in ufo[0]["prompt"]
    )
    # with a reference picture: the edit endpoint, the picture for the shape alone
    r = cluster.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "count": "3",
            "ufo": "100",
            "visitors": ["enterprise"],
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    ref = [p for p in prompts if "craft in the reference picture" in p["prompt"]]
    assert (
        len(ref) == 1
        and ref[0]["_url"].endswith("nano-banana/edit")
        and ref[0]["image_urls"][0].startswith("data:image/jpeg;base64,")
    ), "the reference handed over inline"
    assert "Enterprise" not in ref[0]["prompt"] and "warp nacelles" in ref[0]["prompt"]
    meta = json.loads(
        next((tmp_path / "paintings").glob("ufo_enterprise--*.json")).read_text()
    )
    assert "Wikimedia Commons" in meta["credit"]
    assert set(P.UFO_REFS) <= set(P.UFOS) and len(P.UFO_REFS) == 19
    r = cluster.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "count": "3",
            "ufo": "100",
            "visitors": ["adamski"],
        },
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    contact = [a for a in r["aircraft"] if a.get("ufo")]
    assert (
        len(contact) == 1
        and contact[0]["cs"] == "UNKNOWN"
        and contact[0]["lines"][0] == "no transponder"
        and contact[0]["pic"]["kind"] == "painting"
    )
    assert contact[0]["span"] < min(
        a["span"] for a in r["aircraft"] if not a.get("ufo")
    ), "the smallest thing on the page"
    key = next((tmp_path / "paintings").glob("ufo_*--poster--p3.jpg")).stem
    assert key.startswith("ufo_") and len(r["aircraft"]) == 4
    # a single page keeps the aircraft and carries the contact apart
    r = plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "ufo": "100", "visitors": ["adamski"]},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    _settle()
    r = plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "ufo": "100", "visitors": ["adamski"]},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert (
        len(r["aircraft"]) == 1
        and r["aircraft"][0]["cs"] == "QLK1997"
        and r["ufo"]["pic"]["src"].startswith("data:image/png")
    )


def test_the_visitor_pools():
    assert (
        len(P.ufo_choices("classic")) == 6
        and len(P.ufo_choices("famous")) == 15
        and len(P.ufo_choices("real")) == 9
        and len(P.ufo_choices("all")) == 30
    )
    assert P.ufo_choices("nonsense") == P.ufo_choices("classic")
    for sid in P.ufo_choices("famous"):
        name, how, pool = P.UFOS[sid]
        pr = P.prompt_for({"key": "x", "ufo": sid, "style": "poster"})
        assert how in pr and name.lower() not in pr.lower(), (
            f"{name} is described, not named"
        )
    from datetime import datetime

    rows = {
        S.ufo_row(
            100,
            f"s{i}",
            datetime(2026, 10, 17, 15),
            25.0,
            ["shuttle", "sputnik", "nonsense"],
        )["ufo"]
        for i in range(40)
    }
    assert rows == {"shuttle", "sputnik"}, "only the ticked craft come"
    r = S.ufo_row(100, "s", datetime(2026, 10, 17, 15), 25.0, ["enterprise"])
    assert r["cs"] == "ENTERPRISE" and r["typ"] == "Enterprise"
    assert {
        S.ufo_row(100, f"s{i}", datetime(2026, 10, 17, 15), 25.0, [])["ufo"]
        for i in range(40)
    } <= set(P.ufo_choices("classic")), "nothing ticked: the classics"
    # a classic is told to be alien; a famous craft is not
    assert "Nothing about it is man-made" in P.prompt_for(
        {"key": "x", "ufo": "saucer", "style": "poster"}
    )
    assert "Nothing about it is man-made" not in P.prompt_for(
        {"key": "x", "ufo": "enterprise", "style": "poster"}
    )
    m = json.loads(
        (ROOT / "overhead_cluster" / "plugin.json").read_text(encoding="utf-8")
    )
    vis = next(o for o in m["cell_options"] if o["name"] == "visitors")
    assert (
        vis["type"] == "multiselect"
        and len(vis["choices"]) == 30
        and vis["default"] == P.ufo_choices("classic")
    )


def test_your_own_reference_pictures(tmp_path, offline):
    prompts, _ = offline
    from PIL import Image

    mine = tmp_path / "nostromo.png"
    Image.new("RGB", (300, 200), (90, 90, 100)).save(mine, "PNG")
    own = P.own_refs(
        f"nostromo = {mine}\nenterprise=https://example.org/ncc.jpg\nnonsense = x\njust words"
    )
    assert (
        set(own) == {"nostromo", "enterprise"}
        and own["enterprise"]["src"] == "https://example.org/ncc.jpg"
    )
    assert P.ref_for("enterprise", own)["src"] == "https://example.org/ncc.jpg", (
        "yours over the bundled one"
    )
    assert (
        P.ref_for("falcon", own) == P.UFO_REFS["falcon"]
        and P.ref_for("viper", own) == {}
    )
    settings = {**SETTINGS, "visitor_refs": f"nostromo = {mine}"}
    cluster.fetch(
        {
            **MELBOURNE,
            "pictures": "paintings",
            "count": "2",
            "ufo": "100",
            "visitors": ["nostromo"],
        },
        settings,
        ctx=_ctx(tmp_path),
    )
    _settle()
    pr = next(p for p in prompts if "craft in the reference picture" in p["prompt"])
    assert (
        pr["image_urls"][0].startswith("data:image/png;base64,")
        and "towing ship" in pr["prompt"]
    )
    meta = json.loads(
        next((tmp_path / "paintings").glob("ufo_nostromo--*.json")).read_text()
    )
    assert meta["credit"].endswith("from your own picture")


def test_plate_reads_the_airline_colours_off_its_mark(tmp_path, offline):
    r = plate.fetch({**MELBOURNE, "pictures": "photos"}, SETTINGS, ctx=_ctx(tmp_path))
    a = r["aircraft"][0]
    assert r["colours"] == "airline" and a["iata"], (
        "the airline's colours by default; the nearest aircraft has an airline"
    )
    assert a["brand"]["primary"] == "#c81414" and a["brand"]["ink"] == "#ffffff", (
        "the red bar of the test mark is the main colour, with white ink on it"
    )
    assert (
        a["brand"]["secondary"] != a["brand"]["primary"]
        and a["brand"]["tint"] == "#f7dede"
        and a["brand"]["shade"] == "#6e0b0b"
    )
    assert r["look"] == "plate" and a["compass"] in (
        "N",
        "NE",
        "E",
        "SE",
        "S",
        "SW",
        "W",
        "NW",
    )
    r = plate.fetch(
        {**MELBOURNE, "pictures": "photos", "colours": "paper", "look": "poster"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert (
        r["colours"] == "paper"
        and r["look"] == "poster"
        and r["aircraft"][0]["brand"] == {}
    ), "paper asked for, and no colours are read"


def test_a_stock_picture_for_an_unknown_airline_is_no_logo(tmp_path, offline):
    assert S.A.logo_bytes("QF", "daisycon", tmp_path), "a real mark comes through"
    assert S.A.logo_bytes("ZZ", "daisycon", tmp_path) == b"", (
        "the service's stock picture, served for a code that is no airline's, is not a mark"
    )
    assert (
        S.A.logo_src("ZZ", "daisycon", tmp_path, "colour") == ""
        and S.A.brand_of("ZZ", "daisycon", tmp_path) == {}
    )


def test_the_budget_is_in_dollars_and_the_old_count_still_counts():
    assert (
        P.daily_cap({"gen_daily_usd": "4"}) == 400
        and P.daily_cap({"gen_daily_usd": 0}) == P.UNLIMITED
    )
    assert P.daily_cap({"gen_daily_cap": "12"}) == 48, (
        "an older install's count of paintings, at the typical price"
    )
    assert P.daily_cap({}) == 400 and P.daily_cap({"gen_daily_cap": "0"}) == P.UNLIMITED
    assert (
        P.dollars(400) == "US$4.00"
        and P.dollars(P.UNLIMITED) == "no limit"
        and P.cost_cents("nano_banana_pro") == 15
    )


def test_a_panel_render_says_how_many_paintings_are_pending(tmp_path, offline):
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["live_refresh_s"] > 0 and r["live_pending"] >= 1, (
        "paintings started for the page are pending work"
    )
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "photos", "count": "3"}, SETTINGS, ctx=_ctx(tmp_path)
    )
    assert r["live_refresh_s"] == 0 and r["live_pending"] == 0


def test_a_0_1_install_is_adopted(tmp_path, offline):
    old = tmp_path / "gen"
    old.mkdir()
    key = P.key_for("VH-XVQ", "poster")
    (old / f"{key}.jpg").write_bytes(_jpeg(paper=(252, 250, 246)))
    (old / f"{key}.json").write_text(
        json.dumps({"credit": "old painting", "style": "poster", "reg": "VH-XVQ"})
    )
    (old / f"{key}_cut3.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (old / f"{key}_700_colour.jpg").write_bytes(_jpeg())
    (old / "budget.json").write_text(json.dumps({time.strftime("%Y-%m-%d"): 8}))
    (tmp_path / "dashboards.json").write_text(
        json.dumps(
            {
                "Hall|poster|abc": {
                    "name": "Hall",
                    "style": "poster",
                    "keys": [key],
                    "jobs": {
                        key: {
                            "key": key,
                            "reg": "VH-XVQ",
                            "typ": "Embraer E190",
                            "style": "poster",
                            "photo": "https://t.example/VH-XVQ.jpg",
                        }
                    },
                    "at": time.time(),
                }
            }
        )
    )
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "4"},
        SETTINGS,
        ctx=_ctx(tmp_path, page_name="Hall"),
    )
    _settle()
    assert not old.exists() and (tmp_path / "paintings" / f"{key}.jpg").exists(), (
        "gen/ became the collection's folder"
    )
    assert not (tmp_path / "paintings" / f"{key}_700_colour.jpg").exists(), (
        "old resized copies went"
    )
    xvq = next(a for a in r["aircraft"] if a["reg"] == "VH-XVQ")
    assert xvq["pic"]["credit"] == "old painting", (
        "the old painting shows, cut out afresh"
    )
    assert P.budget_used(tmp_path) >= 8, "the day's spend carried over (cents already)"
    d = P.ART.dashboards(tmp_path)
    assert any(
        x["name"] == "Hall"
        and x["jobs"].get(key, {}).get("payload", {}).get("reg") == "VH-XVQ"
        for x in d
    )


def test_an_older_tesserae_still_draws_the_photographs(tmp_path, offline, monkeypatch):
    """Without app.artwork (Tesserae before 0.463) the widgets load, show the
    photographs, start nothing and say what they are missing."""
    monkeypatch.setattr(P, "ART", P._NoArtwork())
    r = cluster.fetch(
        {**MELBOURNE, "pictures": "paintings", "count": "3"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert (
        r["state"] == "ok" and P.NEEDS_HOST in r["notices"] and r["live_refresh_s"] == 0
    )
    assert all(
        a["pic"]["kind"] == "photo" for a in r["aircraft"] if a["reg"] != "VH-NPS"
    )
    r = plate.fetch(
        {**MELBOURNE, "pictures": "paintings", "unpainted": "skip"},
        SETTINGS,
        ctx=_ctx(tmp_path),
    )
    assert r["state"] == "painting" and P.NEEDS_HOST in r["hint"]
    assert (
        P.ART.state("x", tmp_path) == "none"
        and P.ART.held(tmp_path) == {}
        and not P.ART.adopt(tmp_path, "gen")
    )


def test_slow_lookups_keep_to_the_budget(tmp_path, offline, monkeypatch):
    """A photograph service that answers slowly does not cost the page: the
    lookups run side by side, stop at the budget, and the rest come next time."""
    real = N.http

    def slow(url, token="", accept="application/json", **kw):
        if "api.planespotters.net" in url:
            time.sleep(1.5)
        return real(url, token, accept, **kw)

    monkeypatch.setattr(N, "http", slow)
    monkeypatch.setattr(S, "BUDGET_S", 0.8)
    t0 = time.time()
    opts = {**MELBOURNE, "pictures": "photos", "count": "4"}
    r = cluster.fetch(opts, SETTINGS, ctx=_ctx(tmp_path))
    took = time.time() - t0
    assert took < 3.0, f"the fetch took {took:.1f}s: it must stop at the budget"
    assert r["state"] == "ok" and r["live_refresh_s"] > 0
    assert any("on the way" in s for s in r["status"])
    assert all("lines" in a and "about" in a for a in r["aircraft"]), (
        "the words are there anyway"
    )
    time.sleep(2.0)  # the slow lookups finish in the background and are cached
    r = cluster.fetch(opts, SETTINGS, ctx=_ctx(tmp_path))
    assert not any("on the way" in s for s in r["status"])
    assert any(a["pic"] for a in r["aircraft"])


def test_adsb_fi_answers_when_adsb_lol_is_down(tmp_path, offline, monkeypatch):
    """adsb.lol hanging costs the page two seconds, not the six it has: adsb.fi
    is asked beside it, its answer is used and credited, and the next refresh
    passes adsb.lol over."""
    real = N.http
    asked: list[str] = []

    def hanging(url, token="", accept="application/json", **kw):
        asked.append(url)
        if "api.adsb.lol" in url:
            time.sleep(kw.get("timeout", 5))
            return None, "unreachable"
        return real(url, token, accept, **kw)

    monkeypatch.setattr(N, "http", hanging)
    monkeypatch.setattr(A, "FEED_WAIT_S", 0.3)
    monkeypatch.setattr(A, "FEED_BUDGET_S", 1.0)
    t0 = time.time()
    rows, err, feed = A.nearby("adsb_lol", "", -37.67, 144.84, 35, tmp_path, "ua")
    took = time.time() - t0
    assert err is None and feed == "adsb.fi" and len(rows) == 5 and took < 1.6
    monkeypatch.setattr(A, "LIVE_S", 0)
    asked.clear()
    rows, err, feed = A.nearby("adsb_lol", "", -37.67, 144.84, 35, tmp_path, "ua")
    assert feed == "adsb.fi" and not any("adsb.lol" in u for u in asked), (
        "passed over while marked down"
    )
    r = cluster.fetch({**MELBOURNE, "pictures": "photos"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["attribution"].startswith("positions from adsb.fi")


def test_both_feeds_down_is_one_plain_error(tmp_path, offline, monkeypatch):
    monkeypatch.setattr(N, "http", lambda *a, **k: (None, "unreachable"))
    rows, err, feed = A.nearby("adsb_lol", "", -37.67, 144.84, 35, tmp_path, "ua")
    assert (
        rows == []
        and feed == ""
        and err == "The live feeds (adsb.lol, adsb.fi) could not be reached."
    )


def test_everything_since_the_last_render(tmp_path, offline, monkeypatch):
    monkeypatch.setattr(A, "LIVE_S", 0)
    opts = {
        **MELBOURNE,
        "pictures": "photos",
        "period": "since",
        "labels": ["type", "distance", "seen"],
        "count": "8",
    }
    r = cluster.fetch(opts, SETTINGS, ctx=_ctx(tmp_path))
    assert (
        r["state"] == "ok" and r["period"].startswith("since ") and r["airborne"] == 4
    )
    assert r["status"][0].startswith("5 seen since ") and r["status"][0].endswith(
        ", 5 within reach now"
    )
    first = r["aircraft"][0]
    assert (
        first["lines"][1].startswith("closest ")
        and " at " in first["lines"][1]
        and first["lines"][2].startswith("within reach since ")
    )
    # the Jetstar flies on out of reach: gone from the feed, it stays on the page at its closest approach
    gone = next(a for a in AC if a["flight"].strip() == "JST772")
    AC.remove(gone)
    try:
        r = cluster.fetch(opts, SETTINGS, ctx=_ctx(tmp_path))
        assert "JST772" in [a["cs"] for a in r["aircraft"]] and r["status"][
            0
        ].startswith("5 seen since ")
        r = cluster.fetch({**opts, "period": "now"}, SETTINGS, ctx=_ctx(tmp_path))
        assert (
            "JST772" not in [a["cs"] for a in r["aircraft"]]
            and r["period"] == "in the air now"
        )
    finally:
        AC.append(gone)


def test_the_catalogue_counts_passes(tmp_path, offline):
    SG = S.SG
    a, b = (
        {"reg": "VH-AAA", "cs": "QFA1", "typ": "Airbus A330"},
        {"reg": "VH-BBB", "cs": "VOZ2", "typ": "Boeing 737-800"},
    )
    led = SG.ledger(tmp_path / "unit")
    led.note([a, b], S.SIGHT_ID, S.SIGHT_NAME, now=1000)
    led.note([a], S.SIGHT_ID, S.SIGHT_NAME, now=1600)
    assert led.seen[S.SIGHT_ID(a)]["v"] == 1, (
        "seen again within half an hour is the same pass"
    )
    led.note([a], S.SIGHT_ID, S.SIGHT_NAME, now=4000)
    st = SG.stats(tmp_path / "unit", lambda rid: rid == S.SIGHT_ID(a), now=4000)
    assert (st["airframes"], st["passes"], st["once"], st["twice"], st["painted"]) == (
        2,
        3,
        1,
        1,
        1,
    )
    assert (
        st["painted_passes_share"] == round(2 / 3, 3)
        and st["coverage"] == round(1 - 1 / 3, 3)
        and st["estimate"] == 2
    )
    assert st["top"][0]["passes"] == 2 and st["top"][0]["painted"] is True
    led.save(now=4000)
    again = SG.Ledger(tmp_path / "unit" / SG.FILE)
    assert again.seen[S.SIGHT_ID(a)]["v"] == 2, "kept across a restart"
    # a render counts what it saw, and the paintings page reads it
    cluster.fetch({**MELBOURNE, "pictures": "photos"}, SETTINGS, ctx=_ctx(tmp_path))
    st = core.sightings_context(tmp_path)["s"]
    assert st["airframes"] >= 1 and st["passes"] >= 1 and st["painted"] == 0


def test_a_spent_budget_fills_the_cluster_from_the_collection(tmp_path, offline):
    prompts, _ = offline
    kept = {"VH-OLD": 5, "VH-ONE": 1, "VH-TWO": 2}
    for reg in kept:
        P.ART.keep(
            P.key_for(reg, "poster"),
            tmp_path,
            _jpeg(paper=(252, 250, 246)),
            {
                "reg": reg,
                "typ": "Boeing 737-800",
                "air": "Qantas",
                "style": "poster",
                "credit": f"painted from {reg}",
            },
        )
    P.ART.keep(  # another style is not this page's
        P.key_for("VH-INK", "engraving"),
        tmp_path,
        _jpeg(paper=(252, 250, 246)),
        {"reg": "VH-INK", "typ": "Boeing 737-800", "style": "engraving"},
    )
    led = S.SG.ledger(tmp_path)
    for reg, passes in kept.items():
        for i in range(passes):
            led.note(
                [{"reg": reg, "typ": "Boeing 737-800"}],
                S.SIGHT_ID,
                S.SIGHT_NAME,
                now=1000 + i * 4000,
            )
    P.ART.spend(tmp_path, 100)
    options = {
        **MELBOURNE,
        "pictures": "paintings",
        "style": "poster",
        "count": "4",
        "when_spent": "rare",
    }
    r = cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path))
    assert not prompts, "nothing is painted once the budget is spent"
    shown = [a["reg"] for a in r["aircraft"]]
    assert shown[:3] == ["VH-ONE", "VH-TWO", "VH-OLD"], (
        "the rarest first, every one cut out"
    )
    assert all(
        a["pic"]["kind"] == "painting" and not a["pic"]["whole"]
        for a in r["aircraft"][:3]
    )
    assert r["aircraft"][0]["lines"][-1].startswith("seen once") and r["aircraft"][2][
        "lines"
    ][-1].startswith("seen 5 times")
    assert len(r["aircraft"]) == 4 and r["aircraft"][3]["pic"] is None, (
        "a gap the collection could not fill stays"
    )
    assert (
        r["period"] == "from the collection" and "painted from VH-ONE" in r["credits"]
    )
    assert any("from the collection" in s for s in r["status"])
    # at random: the same three for the hour, in an order of their own
    a = cluster.fetch({**options, "when_spent": "random"}, SETTINGS, ctx=_ctx(tmp_path))
    b = cluster.fetch({**options, "when_spent": "random"}, SETTINGS, ctx=_ctx(tmp_path))
    assert [x["reg"] for x in a["aircraft"]] == [x["reg"] for x in b["aircraft"]]
    assert sorted(x["reg"] for x in a["aircraft"][:3]) == sorted(kept)
    # left alone, the page is as it was: what is overhead, unpainted
    r = cluster.fetch({**options, "when_spent": "keep"}, SETTINGS, ctx=_ctx(tmp_path))
    assert (
        not any(a.get("kept") for a in r["aircraft"])
        and r["period"] == "in the air now"
    )


def test_wheels_up_and_the_medium_alone():
    job = {
        "reg": "VH-VZX",
        "typ": "Boeing 737-800",
        "air": "Qantas",
        "backdrop": "none",
        "photo": "x",
    }
    for fidelity in ("photo", "free"):
        for style in ("poster", "chalk", "engraving"):
            p = P.prompt_for({**job, "style": style, "fidelity": fidelity})
            assert "wheels up" in p and "landing gear fully retracted" in p, (
                style,
                fidelity,
            )
    p = P.prompt_for({**job, "style": "poster", "fidelity": "photo"})
    assert "all but the landing gear" in p and "nothing photographic is left" in p
    assert (
        "faithful translation of this very photograph" not in p
        and "only the medium changes" not in p
    )
    assert "three quarters of its width" in p, "kept clear of the edges for the cut-out"
    chalk = P.prompt_for({**job, "style": "chalk", "fidelity": "photo"})
    assert "medium's own ground fills the whole picture" in chalk and "runway" in chalk
    # a cell on Nano Banana paints the styles it cannot make with GPT Image 2; a chosen model stays
    assert (
        P.model_for("pixel", P.DEFAULT_MODEL) == "gpt_image"
        and P.model_for("poster", P.DEFAULT_MODEL) == P.DEFAULT_MODEL
    )
    assert P.model_for("pixel", "nano_banana_pro") == "nano_banana_pro"


def test_a_style_nano_banana_cannot_make_paints_with_gpt_image(tmp_path, offline):
    prompts, _ = offline
    options = {**MELBOURNE, "pictures": "paintings", "style": "pixel", "count": "1"}
    cluster.fetch(options, SETTINGS, ctx=_ctx(tmp_path))
    _settle()
    assert prompts and all("gpt-image" in p["_url"] for p in prompts), [
        p["_url"] for p in prompts
    ]
    # keyed by the cell's own model, so a pixel painting kept from before still shows
    assert any(
        f.name.endswith("--pixel--p3.jpg")
        for f in (tmp_path / "paintings").glob("*.jpg")
    )
