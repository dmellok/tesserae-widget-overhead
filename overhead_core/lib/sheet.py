"""One fetch for the four Overhead widgets: the aircraft near a place, their
routes, photographs and paintings, and the words for the page. Loaded by
path from each widget's server.py."""

from __future__ import annotations

import contextlib
import hashlib
import random
import importlib.util
import json
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
logger = logging.getLogger("app.plugins.overhead")


def _sibling(name: str) -> Any:
    full = f"_tesserae_plugins.overhead_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


N = _sibling("net")
A = _sibling("adsb")
P = _sibling("paint")
T = _sibling("tray")

WIDGETS = ("photo", "plate", "cluster", "scene")
SOURCES = ("adsb_lol", "receiver")
RADII = ("5", "10", "15", "25", "35", "50", "80")
ORDERS = ("nearest", "lowest", "highest", "largest", "fastest")
PICTURES = ("photos", "paintings")
PANELS = ("colour", "gray16", "gray4", "mono")
PAPERS = ("cream", "white", "aged", "blueprint", "sky")
LABELS = ("airline", "type", "reg", "route", "altitude", "distance", "speed", "heading")
UNPAINTED = ("silhouette", "photo", "skip")
MAX_COUNT = 12
POOL = 6  # the nearest few a single page chooses a painted aircraft from
PICTURE_PX = 700
HERO_PX = 1400
PHOTO_PX = 1600
SETTLE_S = 20
HELD_MAX = 200
ON_FRAME_S = 86400
KEPT_S = 30 * 86400
LIVE_S = 6
_HELD_LOCK = threading.Lock()
# the options that choose what the cell shows, as against how it looks
FONTS = ("fell", "archivo", "georgia", "page")
LOOK_OPTIONS = frozenset(
    ("font", "scale", "fidelity", "ufo", "visitors", "pictures", "style", "custom_style", "build_medium", "build_period", "build_palette", "build_line", "build_texture",
     "build_mood", "build_extra", "model", "backdrop", "view", "unpainted", "logos", "labels", "text_size", "paper",
     "panel", "header", "footer", "title", "strip", "photo_fit")
)
CLASS_ABOUT = {
    "wide": "a wide-body airliner with two aisles",
    "jet": "a single-aisle jet airliner",
    "biz": "a business jet",
    "prop": "a turboprop",
    "light": "a single-engined light aircraft",
    "heli": "a helicopter",
}


def _choice(value: Any, choices: tuple[str, ...], default: str = "") -> str:
    v = str(value or "").strip()
    return v if v in choices else (default if default in choices else choices[0])


def _int(value: Any, default: int, low: int, high: int) -> int:
    with contextlib.suppress(TypeError, ValueError):
        return max(low, min(high, int(float(str(value).strip()))))
    return default


def _tz(options: dict[str, Any]) -> ZoneInfo | None:
    loc = options.get("location")
    name = loc.get("timezone") if isinstance(loc, dict) else ""
    with contextlib.suppress(Exception):
        if name:
            return ZoneInfo(str(name))
    return None


def place_of(options: dict[str, Any], ctx: dict[str, Any]) -> tuple[float, float, str] | None:
    loc = options.get("location")
    label = str(loc.get("label") or "") if isinstance(loc, dict) else ""
    for lat, lon in ((options.get("latitude"), options.get("longitude")), (ctx.get("home_lat"), ctx.get("home_lon"))):
        with contextlib.suppress(TypeError, ValueError):
            la, lo = float(lat), float(lon)
            if la or lo:
                return la, lo, label
    return None


def compass(deg: int) -> str:
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[round(deg / 45) % 8]


def trend_of(r: dict[str, Any]) -> str:
    if r.get("ground"):
        return "on the ground"
    if r["rate"] > 300:
        return "climbing"
    if r["rate"] < -300:
        return "descending"
    return "level"


def where_of(r: dict[str, Any]) -> str:
    return f"{r['km']:g} km {compass(r['dir'])}"


def alt_of(r: dict[str, Any]) -> str:
    return "on the ground" if r.get("ground") else f"{r['alt']:,} ft {trend_of(r)}"


def route_text(r: dict[str, Any]) -> str:
    ro = r.get("route") or {}
    o, d = ro.get("origin_city") or ro.get("origin"), ro.get("dest_city") or ro.get("dest")
    if o and d:
        return f"{o} to {d}"
    if r.get("ground"):
        return "on the ground"
    return "climbing out" if r["rate"] > 300 and r["alt"] < 6000 else "on approach" if r["rate"] < -300 and r["alt"] < 6000 else "passing over"


def lines_for(r: dict[str, Any], labels: list[str]) -> list[str]:
    out: list[str] = []
    for lab in labels:
        if lab == "airline" and r.get("air") and r["air"] != "private":
            out.append(r["air"])
        elif lab == "type":
            out.append(r["typ"])
        elif lab == "reg" and r.get("reg"):
            out.append(r["reg"])
        elif lab == "route":
            out.append(route_text(r))
        elif lab == "altitude":
            out.append(alt_of(r))
        elif lab == "distance":
            out.append(where_of(r))
        elif lab == "speed" and r.get("gs"):
            out.append(f"{r['gs']} kt")
        elif lab == "heading":
            out.append(f"heading {r['trk']:03d}°")
    return out


def ufo_row(chance: int, subject: str, now: datetime, radius: float, chosen: Any = None) -> dict[str, Any] | None:
    """Once an hour the dice are thrown for a page: an unidentified contact,
    with made-up height and bearing, or nothing. The same hour and page always
    throw the same, so the editor's preview and the panel agree."""
    if chance <= 0:
        return None
    rng = random.Random(f"{now.strftime('%Y-%m-%d %H')}|{subject}")
    if rng.random() * 100 >= chance:
        return None
    shape = rng.choice(P.visitors_of(chosen))
    km = round(rng.uniform(1.5, max(2.0, radius * 0.9)), 1)
    deg = rng.randrange(0, 360)
    alt = rng.choice((1200, 2400, 3100, 4700, 6500, 9800, 14000, 31000, 48000))
    return {
        "hex": "", "cs": "UNKNOWN" if P.UFOS[shape][2] == "classic" else P.UFOS[shape][0].upper(), "reg": "", "code": "", "typ": P.UFOS[shape][0], "cls": "ufo", "span": 22.0,
        "alt": alt, "ground": False, "rate": rng.choice((-4000, 0, 0, 0, 9000)), "gs": rng.choice((0, 0, 40, 1800, 3400)), "trk": deg,
        "km": km, "dir": deg, "squawk": "", "military": False, "ufo": shape, "route": {}, "iata": "", "air": "", "photo": {}, "logo": "",
    }


def about_of(r: dict[str, Any]) -> str:
    cls = CLASS_ABOUT.get(r.get("cls") or "jet", "an aircraft") if r.get("typ") != r.get("code") else "an aircraft of a type the widget does not know"
    air = r.get("air") or ""
    who = f", flown by {air}" if air and air != "private" else ""
    ro = r.get("route") or {}
    going = ""
    if ro.get("origin_city") and ro.get("dest_city"):
        going = f" It is on its way from {ro['origin_city']} to {ro['dest_city']}"
        going += f", {trend_of(r)} through {r['alt']:,} ft." if not r.get("ground") else "."
    elif not r.get("ground"):
        going = f" It is {trend_of(r)} at {r['alt']:,} ft, {r['km']:g} km to the {compass(r['dir'])}."
    return f"The {r['typ']} is {cls}{who}.{going}"


# ----------------------------------------------------------------------
# Held paintings, settling previews, the dashboards' records
# ----------------------------------------------------------------------
def subject_id(options: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps({k: v for k, v in sorted(options.items()) if k not in LOOK_OPTIONS}, sort_keys=True, default=str).encode()).hexdigest()[:16]


def cell_id(options: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(sorted(options.items()), sort_keys=True, default=str).encode()).hexdigest()[:16]


def preview_settled(data_dir: Path, cell: str, now: float) -> bool:
    path = data_dir / "preview_seen.json"
    seen = N.read_json(path, {})
    seen = {k: float(v) for k, v in seen.items() if isinstance(v, (int, float)) and now - float(v) < ON_FRAME_S} if isinstance(seen, dict) else {}
    first = seen.get(cell)
    if first is None:
        seen[cell] = now
        N.write(path, json.dumps(seen).encode())
        return False
    return now - first >= SETTLE_S


def held(data_dir: Path) -> dict[str, dict[str, Any]]:
    got = N.read_json(data_dir / "held_paints.json", {})
    return got if isinstance(got, dict) else {}


def _hold(data_dir: Path, job: dict[str, Any]) -> None:
    with _HELD_LOCK:
        got = held(data_dir)
        if job["key"] in got:
            return
        got[job["key"]] = job
        for old in list(got)[: max(0, len(got) - HELD_MAX)]:
            del got[old]
        N.write(data_dir / "held_paints.json", json.dumps(got).encode())


def _unhold(data_dir: Path, keys: list[str] | None = None) -> None:
    with _HELD_LOCK:
        got = held(data_dir)
        for k in keys if keys is not None else list(got):
            got.pop(k, None)
        N.write(data_dir / "held_paints.json", json.dumps(got).encode())


def start_held(data_dir: Path, fal_key: str, cap: int, subject: str = "") -> int:
    folder = P.gen_dir(data_dir)
    jobs = [j for j in held(data_dir).values() if not subject or j.get("subject") == subject]
    _unhold(data_dir, [j["key"] for j in jobs])
    ready = [j for j in jobs if P.state(j["key"], folder) == "none"]
    room = max(0, cap - P.budget_used(folder))
    begin = ready[:room]
    P.start_batch(begin, data_dir, fal_key, cap)
    T.waiting_over(len(begin))
    return len(begin)


def cull(data_dir: Path, subject: str, keep: set[str]) -> None:
    stale = [k for k, j in held(data_dir).items() if j.get("subject") == subject and k not in keep]
    if stale:
        _unhold(data_dir, stale)
    gone = P.cull_queued(subject, keep)
    if stale or gone:
        logger.info("overhead: dropped %d queued, %d held painting(s) for a look no longer wanted", len(gone), len(stale))


def note_dashboard(data_dir: Path, ctx: dict[str, Any], subject: str, style: str, jobs: dict[str, dict[str, Any]]) -> None:
    path = data_dir / "dashboards.json"
    now = time.time()
    got = N.read_json(path, {})
    got = {k: v for k, v in (got.items() if isinstance(got, dict) else []) if isinstance(v, dict) and now - float(v.get("at") or 0) < KEPT_S}
    name = " ".join(str(ctx.get("page_name") or "").split())[:80]
    rid = f"{name}|{style}|{subject}"
    got = {k: v for k, v in got.items() if not (v.get("name") == name and v.get("style") == style and k != rid and now - float(v.get("at") or 0) > 3600)}
    got[rid] = {"name": name, "icon": str(ctx.get("page_icon") or "")[:40], "style": style, "style_label": P.style_of(style)[0], "keys": list(jobs), "jobs": jobs, "at": now}
    N.write(path, json.dumps(got, ensure_ascii=False).encode())


def dashboards(data_dir: Path) -> list[dict[str, Any]]:
    got = N.read_json(data_dir / "dashboards.json", {})
    if not isinstance(got, dict):
        return []
    now = time.time()
    out = [{**v, "id": k} for k, v in got.items() if isinstance(v, dict) and now - float(v.get("at") or 0) < KEPT_S]
    return sorted(out, key=lambda v: -float(v.get("at") or 0))


def render_now(data_dir: Path, fal_key: str, cap: int, who: str = "") -> tuple[int, int]:
    folder = P.gen_dir(data_dir)
    now = time.time()
    jobs: dict[str, dict[str, Any]] = {}
    for d in dashboards(data_dir):
        if who and d["id"] != who:
            continue
        if not who and now - float(d.get("at") or 0) > ON_FRAME_S:
            continue
        for key, job in (d.get("jobs") or {}).items():
            if isinstance(job, dict) and job.get("key") == key:
                jobs.setdefault(key, {**job, "origin": "panel"})
    ready = [j for j in jobs.values() if not (folder / f"{j['key']}.jpg").exists()]
    room = max(0, cap - P.budget_used(folder))
    begin = [j for j in ready if P.state(j["key"], folder) == "none"][:room]
    P.start_batch(begin, data_dir, fal_key, cap)
    return len(begin), len(ready)


# ----------------------------------------------------------------------
# The fetch
# ----------------------------------------------------------------------
def fetch(options: dict[str, Any], settings: dict[str, Any], ctx: dict[str, Any], widget: str) -> dict[str, Any]:
    widget = widget if widget in WIDGETS else "cluster"
    settings = settings or {}
    data_dir = Path(ctx.get("data_dir") or ".")
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
    preview = bool(ctx.get("preview"))
    ua = A.user_agent(str(settings.get("contact") or ""))
    fal_key = str(settings.get("fal_api_key") or "").strip()
    P.configure(settings)
    cap = P.daily_cap(settings)

    source = _choice(options.get("source"), SOURCES)
    radius = float(_choice(options.get("radius_km"), RADII, "25"))
    order = _choice(options.get("order"), ORDERS)
    count = _int(options.get("count"), 8, 1, MAX_COUNT)
    if widget in ("photo", "plate", "scene"):
        count = 1 + (_int(options.get("strip"), 5, 0, 8) if widget == "photo" else 0)
    include_ground = str(options.get("include_ground") or "").lower() in ("1", "true", "yes", "on")
    pictures = _choice(options.get("pictures"), PICTURES) if widget != "photo" else "photos"
    panel = _choice(options.get("panel"), PANELS)
    paper = _choice(options.get("paper"), PAPERS)
    labels = [x for x in (options.get("labels") or ["type", "route", "altitude", "distance"]) if x in LABELS] if isinstance(options.get("labels"), list) else ["type", "route", "altitude", "distance"]
    logos_on = str(options.get("logos") or "off") == "on"
    logo_source = str(settings.get("logo_source") or "daisycon")
    header = _choice(options.get("header"), ("top", "bottom", "hidden"))
    footer = _choice(options.get("footer"), ("show", "credits", "hide"))
    text_size = _int(options.get("text_size"), 100, 60, 150)
    style = str(options.get("style") or "poster")
    how = ""
    if style == "builder":
        how = P.build_how(options)
        style = P.register_custom(how)
    elif style == "custom":
        words = " ".join(str(options.get("custom_style") or "").split())[:600] or P.CUSTOM_EXAMPLE
        how = words
        style = P.register_custom(how)
    elif style not in P.STYLES:
        style = "poster"
    model = P.model_of(str(options.get("model") or P.DEFAULT_MODEL))
    backdrop = _choice(options.get("backdrop"), tuple(P.BACKDROPS))
    if widget == "cluster":
        backdrop = "none"
    if widget == "scene" and backdrop == "none":
        backdrop = "sky"
    view = _choice(options.get("view"), tuple(P.VIEWS))
    fidelity = _choice(options.get("fidelity"), P.FIDELITIES)
    sky = ""
    sky_words = ""

    tz = _tz(options)
    now = datetime.now(tz) if tz else datetime.now().astimezone()
    place = place_of(options, ctx)
    title = " ".join(str(options.get("title") or "").split()) or (place[2] if place and place[2] else "Overhead")
    base: dict[str, Any] = {
        "widget": widget, "state": "ok", "title": title, "area": f"within {radius:g} km", "period": "in the air now",
        "date": now.strftime("%a %-d %b") if sys.platform != "win32" else now.strftime("%a %d %b"), "time": now.strftime("%H:%M"),
        "aircraft": [], "airborne": 0, "shown": 0, "notices": [], "status": [], "credits": [], "live_refresh_s": 0,
        "header": header, "footer": footer, "paper": paper, "panel": panel, "text_size": text_size, "labels": labels,
        "logos": logos_on, "pictures": pictures, "style": style, "style_label": P.style_of(style)[0], "backdrop": backdrop,
        "photo_fit": _choice(options.get("photo_fit"), ("cover", "contain")), "font_css": N.font_css(("im_fell", "im_fell_sc", "archivo_narrow")),
        "font": _choice(options.get("font"), FONTS), "scale": _int(options.get("scale"), 100, 40, 100),
    }
    if not place:
        return {**base, "state": "error", "error": "Set a place: the cell's location, or the app's location in Settings."}

    if backdrop == "live" and pictures == "paintings":
        tod, wx = A.sky_now(place[0], place[1], now.hour * 60 + now.minute, data_dir, ua)
        sky, sky_words = f"{tod}_{wx}", A.sky_words(tod, wx)
        base["sky"] = {"time": tod, "weather": wx}
    rows, err = A.nearby(source, str(options.get("receiver_url") or ""), place[0], place[1], radius, data_dir, ua)
    if err and not rows:
        return {**base, "state": "error", "error": err}
    airborne = [r for r in rows if not r["ground"]]
    base["airborne"] = len(airborne)
    if not include_ground:
        rows = airborne
    if order == "lowest":
        rows.sort(key=lambda r: (r["ground"], r["alt"], r["km"]))
    elif order == "highest":
        rows.sort(key=lambda r: (-r["alt"], r["km"]))
    elif order == "largest":
        rows.sort(key=lambda r: (-r["span"], r["km"]))
    elif order == "fastest":
        rows.sort(key=lambda r: (-r["gs"], r["km"]))
    unpainted = _choice(options.get("unpainted"), UNPAINTED, "photo" if widget in ("plate", "scene") else "silhouette")
    only_painted = pictures == "paintings" and unpainted == "skip"
    # only painted aircraft: a single page looks among the nearest few for one already painted,
    # and keeps painting them, so a page has one most of the time
    pool = rows[: max(count, POOL) if only_painted else count]
    shown = pool
    if not shown:
        return {**base, "state": "empty", "hint": "Nothing within reach right now. A wider radius, or aircraft on the ground, would show more."}

    # the unidentified contact, now and then
    ufo = ufo_row(_int(options.get("ufo"), 0, 0, 100), subject_id(options), now, radius, options.get("visitors")) if pictures == "paintings" and widget != "photo" else None
    if ufo:
        shown = shown + [ufo] if widget == "cluster" else shown[:1] + [ufo]
    # routes, operators, photographs
    for r in shown:
        if r.get("ufo"):
            r["lines"] = ["no transponder", f"{r['alt']:,} ft" + (" climbing" if r["rate"] > 0 else " descending" if r["rate"] < 0 else ""), f"{r['km']:g} km {compass(r['dir'])}"]
            r["alt_text"], r["where"], r["trend"], r["route_text"] = f"{r['alt']:,} ft", f"{r['km']:g} km {compass(r['dir'])}", "unknown", "no transponder"
            r["about"] = "An unidentified object with no transponder, no flight plan and no explanation."
            r["sil"] = "/plugins/overhead_core/static/sil/ufo.svg"
            continue
        r["route"] = A.route_of(r["cs"], data_dir, ua) if r["cs"] != r["reg"] else {}
        iata, air = A.airline_of(r["cs"], r["reg"], (r["route"] or {}).get("airline") or "")
        r["iata"], r["air"] = iata, air
        r["photo"] = A.photo_of(r["reg"], data_dir, ua) if r["reg"] else {}
        r["logo"] = A.logo_src(iata, logo_source, data_dir, panel) if logos_on and iata else ""
        r["lines"] = lines_for(r, labels)
        r["alt_text"], r["where"], r["trend"], r["route_text"] = alt_of(r), where_of(r), trend_of(r), route_text(r)
        r["about"] = about_of(r)
        r["sil"] = f"/plugins/overhead_core/static/sil/{r['cls']}.svg"

    credits: list[str] = []
    px = PHOTO_PX if widget in ("photo", "scene") else HERO_PX if widget == "plate" else PICTURE_PX
    states: dict[str, int] = {}
    subject = subject_id(options)
    cell = cell_id(options)
    hold = preview and not preview_settled(data_dir, cell, time.time())
    per_fetch = P.per_fetch() if preview else len(pool)  # a panel paints what its page could show
    started = 0
    jobs: dict[str, dict[str, Any]] = {}
    folder = P.gen_dir(data_dir)
    whole_ = backdrop != "none" or style in P.OWN_PAPER
    for r in shown:
        photo = r.get("photo") or {}
        pic: dict[str, Any] | None = None
        if pictures == "paintings" and r.get("ufo"):
            key = P.ufo_key(r["ufo"], style)
            job = {"key": key, "ufo": r["ufo"], "style": style, "how": how, "backdrop": "none", "model": model, "photo": "", "aspect": "4:3", "subject": subject, "origin": "preview" if preview else "panel"}
            jobs[key] = job
            pic = P.picture(key, folder, px, panel, style in P.OWN_PAPER)
            if pic:
                states["painted"] = states.get("painted", 0) + 1
            else:
                go, why = P.may_start(key, folder, fal_key, cap)
                if go and hold:
                    _hold(data_dir, job)
                    why = "held"
                elif go and started < per_fetch:
                    if P.start(dict(job), data_dir, fal_key, cap):
                        started += 1
                        why = "running"
                        _unhold(data_dir, [key])
                elif go:
                    why = "waiting"
                states["paint_" + (why or "waiting")] = states.get("paint_" + (why or "waiting"), 0) + 1
            r["pic"] = pic
            continue
        if pictures == "paintings":
            key = P.key_for(r["reg"] or r["cs"], style, backdrop, view, model, sky, fidelity)
            job = {
                "key": key, "reg": r["reg"] or r["cs"], "typ": r["typ"], "air": r["air"] if r["air"] != "private" else "", "style": style, "how": how,
                "backdrop": backdrop, "sky_words": sky_words, "view": view, "fidelity": fidelity, "model": model, "photo": photo.get("src") or "", "by": photo.get("by") or "",
                "link": photo.get("link") or "", "aspect": "4:3", "subject": subject, "origin": "preview" if preview else "panel",
            }
            if photo.get("src"):
                jobs[key] = job  # what this page asks for, for Render now; nothing without a photograph
            pic = P.picture(key, folder, px, panel, whole_)
            if pic:
                states["painted"] = states.get("painted", 0) + 1
                if pic.get("credit"):
                    credits.append(pic["credit"])
            elif not photo.get("src"):
                states["no_photo"] = states.get("no_photo", 0) + 1
            else:
                go, why = P.may_start(key, folder, fal_key, cap)
                if go and hold:
                    _hold(data_dir, job)
                    why = "held"
                elif go and started < per_fetch:
                    if P.start(dict(job), data_dir, fal_key, cap):
                        started += 1
                        why = "running"
                        _unhold(data_dir, [key])
                elif go:
                    why = "waiting"
                states["paint_" + (why or "waiting")] = states.get("paint_" + (why or "waiting"), 0) + 1
                if why == "failed":
                    r["why"] = P.why_failed(key, folder)
        # the photograph: asked for, or shown until the painting lands, or for want of a key
        if pic is None and photo.get("src") and not only_painted and (pictures == "photos" or unpainted == "photo" or not fal_key or widget in ("photo", "plate", "scene")):
            src = A.photo_src(photo, data_dir, ua, px, panel)
            if src:
                pic = {"src": src, "kind": "photo", "whole": True, "credit": f"photo by {photo.get('by') or 'a planespotter'} (planespotters.net)", "aspect": N.aspect_of(src), "link": photo.get("link") or ""}
                credits.append(pic["credit"])
        r["pic"] = pic
        r.pop("lat", None)
        r.pop("lon", None)
    if widget != "cluster":
        contact = next((r for r in shown if r.get("ufo")), None)
        shown = [r for r in shown if not r.get("ufo")]
        if contact and contact.get("pic"):
            base["ufo"] = contact
    elif only_painted:
        pass
    if only_painted:
        painted_rows = [r for r in shown if r.get("pic") and r["pic"].get("kind") == "painting"]
        shown = painted_rows[:count]
    elif widget == "cluster":
        shown = [r for r in shown if not r.get("ufo") or r.get("pic")]  # an unpainted contact is no contact
    base["aircraft"] = shown
    base["shown"] = len(shown)

    notices, status = [], []
    if pictures == "paintings":
        if states.get("paint_running") or states.get("paint_waiting"):
            status.append(f"painting {min(states.get('painted', 0) + 1, len(pool))} of {len(pool)}")
        if states.get("paint_held"):
            n = len([j for j in held(data_dir).values() if j.get("subject") == subject])
            status.append(f"{n} painting{'' if n == 1 else 's'} waiting for Paint now in the job tray")
            T.waiting(n, lambda: start_held(data_dir, fal_key, cap, subject))
        if states.get("paint_no_key"):
            notices.append(P.NOTE_NO_KEY)
        if states.get("paint_capped"):
            status.append(P.NOTE_GEN_CAP.format(cap=cap))
        if states.get("paint_failed"):
            n = states["paint_failed"]
            notices.append(f"{n} painting{'' if n == 1 else 's'} failed; tried again later")
        if states.get("no_photo"):
            n = states["no_photo"]
            status.append(f"{n} without a photograph to paint from")
        if preview:
            cull(data_dir, subject, set(jobs))
        elif jobs:
            note_dashboard(data_dir, ctx, subject, style, jobs)
    if err:
        notices.append(err)
    busy = any(k in states for k in ("paint_running", "paint_waiting", "paint_held"))
    if only_painted and not shown:
        waiting = states.get("paint_running", 0) + states.get("paint_waiting", 0) + states.get("paint_held", 0)
        base.update(state="painting", notices=notices, status=status, live_refresh_s=LIVE_S if busy else 0, airborne=len(airborne))
        base["hint"] = (
            f"Painting {waiting} of the aircraft overhead; the page fills as they land." if waiting
            else P.NOTE_NO_KEY if states.get("paint_no_key") else "Nothing overhead is painted yet."
        )
        return base
    base.update(
        notices=notices, status=status, credits=list(dict.fromkeys(credits))[:4], live_refresh_s=LIVE_S if busy else 0,
        airborne=len(airborne), attribution="positions from adsb.lol" if source == "adsb_lol" else "positions from your receiver",
    )
    logger.info(
        "overhead: %s %s, %d near, %d shown, painted %d, started %d, held %d, no photo %d",
        "preview" if preview else "panel", widget, len(rows), len(shown), states.get("painted", 0), started, states.get("paint_held", 0), states.get("no_photo", 0),
    )
    return base
