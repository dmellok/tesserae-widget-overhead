"""One fetch for the four Overhead widgets: the aircraft near a place, their
routes, photographs and paintings, and the words for the page. Loaded by
path from each widget's server.py."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
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
W = _sibling("watch")
SG = _sibling("sightings")
# the ledger of passes: one id per airframe (vehicle), the same as the first part of its painting's key
SIGHT_ID = lambda r: r.get("reg") or r.get("cs") or ""
SIGHT_NAME = lambda r: " · ".join(
    x for x in (r.get("reg") or r.get("cs") or "", r.get("typ") or "") if x
)

WIDGETS = ("photo", "plate", "cluster", "scene")
SOURCES = ("adsb_lol", "receiver")
RADII = ("5", "10", "15", "25", "35", "50", "80")
ORDERS = ("nearest", "lowest", "highest", "largest", "fastest")
PICTURES = ("photos", "paintings")
PANELS = ("colour", "gray16", "gray4", "mono")
PAPERS = ("cream", "white", "aged", "blueprint", "sky")
LABELS = (
    "airline",
    "type",
    "reg",
    "route",
    "altitude",
    "distance",
    "speed",
    "heading",
    "seen",
)
PERIODS = ("now", "since")
WATCH_FEED_S = 60  # the community feeds are asked this often while a page watches
WATCH_RECEIVER_S = 30
GONE_S = 120  # an aircraft not seen for this long has passed
UNPAINTED = ("silhouette", "photo", "skip")
# the cluster, when the day's budget is spent: the aircraft that could not be painted give way to
# paintings already kept, chosen at random or the rarest seen first
SPENT = ("keep", "random", "rare")
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
# The composer gives a widget six seconds; the lookups a page needs (routes, photographs,
# marks) run side by side and stop asking at this point, the rest waiting for the next refresh
BUDGET_S = 4.2
# the options that choose what the cell shows, as against how it looks
FONTS = ("fell", "archivo", "georgia", "page")
LOOKS = ("plate", "pass", "tiles", "poster", "split")
LOOK_OPTIONS = frozenset(
    (
        "font",
        "scale",
        "fidelity",
        "ufo",
        "visitors",
        "pictures",
        "style",
        "custom_style",
        "build_medium",
        "build_period",
        "build_palette",
        "build_line",
        "build_texture",
        "build_mood",
        "build_extra",
        "model",
        "backdrop",
        "view",
        "unpainted",
        "logos",
        "labels",
        "text_size",
        "paper",
        "panel",
        "header",
        "footer",
        "title",
        "strip",
        "photo_fit",
        "colours",
        "look",
        "when_spent",
    )
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


def place_of(
    options: dict[str, Any], ctx: dict[str, Any]
) -> tuple[float, float, str] | None:
    loc = options.get("location")
    label = str(loc.get("label") or "") if isinstance(loc, dict) else ""
    for lat, lon in (
        (options.get("latitude"), options.get("longitude")),
        (ctx.get("home_lat"), ctx.get("home_lon")),
    ):
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
    if r.get("closest_text"):
        return f"closest {r['km']:g} km {compass(r['dir'])} at {r['closest_text']}"
    return f"{r['km']:g} km {compass(r['dir'])}"


def seen_of(r: dict[str, Any]) -> str:
    """When it was within reach: the span of a watched sighting, or just now."""
    return r.get("seen_text") or "in the air now"


def alt_of(r: dict[str, Any]) -> str:
    return "on the ground" if r.get("ground") else f"{r['alt']:,} ft {trend_of(r)}"


def route_text(r: dict[str, Any]) -> str:
    ro = r.get("route") or {}
    o, d = (
        ro.get("origin_city") or ro.get("origin"),
        ro.get("dest_city") or ro.get("dest"),
    )
    if o and d:
        return f"{o} to {d}"
    if r.get("ground"):
        # the altitude line already says "on the ground"; this one says what it is doing there
        gs = r.get("gs") or 0
        return "on the runway" if gs >= 40 else "taxiing" if gs >= 3 else "parked"
    return (
        "climbing out"
        if r["rate"] > 300 and r["alt"] < 6000
        else "on approach"
        if r["rate"] < -300 and r["alt"] < 6000
        else "passing over"
    )


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
        elif lab == "seen":
            out.append(seen_of(r))
    return out


def ufo_row(
    chance: int, subject: str, now: datetime, radius: float, chosen: Any = None
) -> dict[str, Any] | None:
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
        "hex": "",
        "cs": "UNKNOWN" if P.UFOS[shape][2] == "classic" else P.UFOS[shape][0].upper(),
        "reg": "",
        "code": "",
        "typ": P.UFOS[shape][0],
        "cls": "ufo",
        "span": 5.0,  # the smallest thing on the page
        "alt": alt,
        "ground": False,
        "rate": rng.choice((-4000, 0, 0, 0, 9000)),
        "gs": rng.choice((0, 0, 40, 1800, 3400)),
        "trk": deg,
        "km": km,
        "dir": deg,
        "squawk": "",
        "military": False,
        "ufo": shape,
        "route": {},
        "iata": "",
        "air": "",
        "photo": {},
        "logo": "",
    }


def about_of(r: dict[str, Any]) -> str:
    cls = (
        CLASS_ABOUT.get(r.get("cls") or "jet", "an aircraft")
        if r.get("typ") != r.get("code")
        else "an aircraft of a type the widget does not know"
    )
    air = r.get("air") or ""
    who = f", flown by {air}" if air and air != "private" else ""
    ro = r.get("route") or {}
    going = ""
    if ro.get("origin_city") and ro.get("dest_city"):
        going = f" It is on its way from {ro['origin_city']} to {ro['dest_city']}"
        going += (
            f", {trend_of(r)} through {r['alt']:,} ft." if not r.get("ground") else "."
        )
    elif not r.get("ground"):
        going = f" It is {trend_of(r)} at {r['alt']:,} ft, {r['km']:g} km to the {compass(r['dir'])}."
    return f"The {r['typ']} is {cls}{who}.{going}"


# ----------------------------------------------------------------------
# Held paintings, settling previews, the dashboards' records
# ----------------------------------------------------------------------
def watched(
    options: dict[str, Any],
    source: str,
    place: tuple[Any, ...],
    radius: float,
    data_dir: Path,
    ua: str,
    rows: list[dict[str, Any]],
    now: datetime,
    preview: bool,
    base: dict[str, Any],
    tz: Any,
) -> list[dict[str, Any]]:
    """Everything seen since this cell's last render: the watch on the place is
    started or kept, what this render saw is noted on it, and the aircraft in
    the window come back at their closest approach, with when that was and
    whether they are still within reach."""
    receiver_url = str(options.get("receiver_url") or "")
    lat, lon = place[0], place[1]
    key = f"overhead|{source}|{receiver_url}|{lat:.3f}|{lon:.3f}|{radius:g}"

    def poll() -> list[dict[str, Any]]:
        got, _err, _feed = A.nearby(
            source, receiver_url, lat, lon, radius, data_dir, ua
        )
        SG.ledger(data_dir).note(got, SIGHT_ID, SIGHT_NAME)
        return got

    w = W.watch_for(
        key,
        poll,
        WATCH_RECEIVER_S if source == "receiver" else WATCH_FEED_S,
        data_dir,
        lambda r: str(r.get("hex") or r.get("reg") or r.get("cs") or ""),
    )
    ts = now.timestamp()
    w.note(rows, ts)
    t0 = W.window(data_dir, subject_id(options), ts, advance=not preview)
    out = w.since(t0, ts)
    for r in out:
        here = ts - r["seen_last"] < GONE_S
        r["closest_text"] = W.clock(r["closest_at"], tz)
        r["seen_text"] = (
            f"within reach since {W.clock(r['seen_first'], tz)}"
            if here
            else f"passed {W.clock(r['seen_first'], tz)} to {W.clock(r['seen_last'], tz)}"
        )
        r["present"] = here
    since = W.clock(t0, tz)
    base["period"] = f"since {since}"
    base["since"] = t0
    base["watch"] = {
        "since": since,
        "seen": len(out),
        "polls": w.polls,
        "error": w.error,
        "present": sum(1 for r in out if r["present"]),
    }
    return out


def _when(t: float, now: datetime) -> str:
    d = (
        datetime.fromtimestamp(t, now.tzinfo)
        if now.tzinfo
        else datetime.fromtimestamp(t)
    )
    return d.strftime("%-d %b" if sys.platform != "win32" else "%d %b")


def from_collection(
    art: Any,
    data_dir: Path,
    *,
    style: str,
    exclude: set[str],
    n: int,
    mode: str,
    seed: str,
    labels: list[str],
    px: int,
    panel: str,
    whole_: bool,
    deadline: float,
    now: datetime,
) -> list[dict[str, Any]]:
    """Up to ``n`` kept paintings in this style, for the gaps a spent budget
    leaves on the cluster: in an order of their own that holds for the hour
    (random), or those seen fewest times first (rare). One per aircraft, none
    already on the page. Cutting out a painting never cut before stops at
    the deadline; those already cut keep coming."""
    c = art.c
    if c is None or n <= 0:
        return []
    led = SG.ledger(data_dir)
    with led.lock:
        seen = {N.slug(k): dict(v) for k, v in led.seen.items()}
    folder = c.folder(data_dir)
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    with contextlib.suppress(OSError):
        for f in folder.iterdir():
            if f.suffix not in (".jpg", ".png") or "__" in f.stem or not f.is_file():
                continue
            meta = c.meta(f.stem, data_dir)
            if (
                meta.get("ufo")
                or meta.get("style") != style
                or (meta.get("backdrop") or "none") != "none"
            ):
                continue
            reg = str(meta.get("reg") or "")
            if not reg or N.slug(reg) in exclude or N.slug(reg) in found:
                continue
            found[N.slug(reg)] = (f.stem, meta)
    rng = random.Random(f"{seed}|{now.strftime('%Y-%m-%d %H')}")
    order = sorted(found)
    rng.shuffle(order)
    if mode == "rare":
        order.sort(key=lambda s: int((seen.get(s) or {}).get("v") or 1))
    names = {v[0]: (v[1], v[2]) for v in A.TYPES.values()}
    out: list[dict[str, Any]] = []
    for s in order:
        if len(out) >= n:
            break
        key, meta = found[s]
        if (
            not whole_
            and time.time() > deadline
            and not (folder / f"{key}__cut{P.CUT_VERSION}.png").exists()
        ):
            continue
        pic = P.picture(art, key, px, panel, whole_)
        if not pic:
            continue
        reg, typ, air = (
            str(meta["reg"]),
            str(meta.get("typ") or "Aircraft"),
            str(meta.get("air") or ""),
        )
        cls, span = names.get(typ, ("jet", A.CLASS_SPAN["jet"]))
        e = seen.get(s) or {}
        v = int(e.get("v") or 0)
        when = (
            f"seen once, {_when(float(e['l']), now)}"
            if v == 1 and e.get("l")
            else f"seen {v} times, last {_when(float(e['l']), now)}"
            if v and e.get("l")
            else "from the collection"
        )
        lines = [
            x
            for lab, x in (("airline", air), ("type", typ))
            if lab in labels and x and x != "private"
        ] + [when]
        out.append(
            {
                "reg": reg,
                "cs": reg,
                "typ": typ,
                "air": air,
                "cls": cls,
                "span": span,
                "lines": lines,
                "pic": pic,
                "kept": True,
                "rare": v == 1,
            }
        )
    return out


def subject_id(options: dict[str, Any]) -> str:
    return hashlib.sha1(
        json.dumps(
            {k: v for k, v in sorted(options.items()) if k not in LOOK_OPTIONS},
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:16]


def cell_id(options: dict[str, Any]) -> str:
    return hashlib.sha1(
        json.dumps(sorted(options.items()), sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


# ----------------------------------------------------------------------
# The fetch
# ----------------------------------------------------------------------
def fetch(
    options: dict[str, Any], settings: dict[str, Any], ctx: dict[str, Any], widget: str
) -> dict[str, Any]:
    widget = widget if widget in WIDGETS else "cluster"
    fetch_started = time.time()
    settings = settings or {}
    data_dir = Path(ctx.get("data_dir") or ".")
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
    preview = bool(ctx.get("preview"))
    ua = A.user_agent(str(settings.get("contact") or ""))
    P.adopt_old_install(
        data_dir
    )  # a 0.1.x install's gen/ folder becomes the collection's, once
    art = P.ART.open(
        ctx, settings, subject=subject_id(options)
    )  # Tesserae's store, budget, queue and hold
    fal_key = art.key

    source = _choice(options.get("source"), SOURCES)
    radius = float(_choice(options.get("radius_km"), RADII, "25"))
    order = _choice(options.get("order"), ORDERS)
    count = _int(options.get("count"), 8, 1, MAX_COUNT)
    if widget in ("photo", "plate", "scene"):
        count = 1 + (_int(options.get("strip"), 5, 0, 8) if widget == "photo" else 0)
    include_ground = str(options.get("include_ground") or "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    pictures = (
        _choice(options.get("pictures"), PICTURES) if widget != "photo" else "photos"
    )
    panel = _choice(options.get("panel"), PANELS)
    paper = _choice(options.get("paper"), PAPERS)
    labels = (
        [
            x
            for x in (
                options.get("labels") or ["type", "route", "altitude", "distance"]
            )
            if x in LABELS
        ]
        if isinstance(options.get("labels"), list)
        else ["type", "route", "altitude", "distance"]
    )
    logos_on = str(options.get("logos") or "off") == "on"
    colours = (
        _choice(options.get("colours"), ("paper", "airline"), "airline")
        if widget == "plate"
        else "paper"
    )
    look = (
        _choice(options.get("look"), LOOKS, "plate") if widget == "plate" else "plate"
    )
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
        words = (
            " ".join(str(options.get("custom_style") or "").split())[:600]
            or P.CUSTOM_EXAMPLE
        )
        how = words
        style = P.register_custom(how)
    elif style not in P.STYLES:
        style = "poster"
    model = P.model_of(str(options.get("model") or P.DEFAULT_MODEL))
    # the painting is keyed by the cell's model, so one kept before a style moved to another
    # model still shows; a new one is made with the model the style needs
    paint_model = P.model_for(style, model)
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
    title = " ".join(str(options.get("title") or "").split()) or (
        place[2] if place and place[2] else "Overhead"
    )
    base: dict[str, Any] = {
        "widget": widget,
        "state": "ok",
        "title": title,
        "area": f"within {radius:g} km",
        "period": "in the air now",
        "date": now.strftime("%a %-d %b")
        if sys.platform != "win32"
        else now.strftime("%a %d %b"),
        "time": now.strftime("%H:%M"),
        "aircraft": [],
        "airborne": 0,
        "shown": 0,
        "notices": [],
        "status": [],
        "credits": [],
        "live_refresh_s": 0,
        "header": header,
        "footer": footer,
        "paper": paper,
        "panel": panel,
        "text_size": text_size,
        "labels": labels,
        "logos": logos_on,
        "colours": colours,
        "look": look,
        "pictures": pictures,
        "style": style,
        "style_label": P.style_of(style)[0],
        "backdrop": backdrop,
        "photo_fit": _choice(options.get("photo_fit"), ("cover", "contain")),
        "font_css": N.font_css(("im_fell", "im_fell_sc", "archivo_narrow")),
        "font": _choice(options.get("font"), FONTS),
        "scale": _int(options.get("scale"), 100, 40, 100),
    }
    if not place:
        return {
            **base,
            "state": "error",
            "error": "Set a place: the cell's location, or the app's location in Settings.",
        }

    if backdrop == "live" and pictures == "paintings":
        tod, wx = A.sky_now(
            place[0], place[1], now.hour * 60 + now.minute, data_dir, ua
        )
        sky, sky_words = f"{tod}_{wx}", A.sky_words(tod, wx)
        base["sky"] = {"time": tod, "weather": wx}
    rows, err, feed = A.nearby(
        source,
        str(options.get("receiver_url") or ""),
        place[0],
        place[1],
        radius,
        data_dir,
        ua,
    )
    if err and not rows:
        return {**base, "state": "error", "error": err}
    SG.ledger(data_dir).note(rows, SIGHT_ID, SIGHT_NAME)
    period = _choice(options.get("period"), PERIODS, "now")
    if period == "since" and not err:
        rows = watched(
            options, source, place, radius, data_dir, ua, rows, now, preview, base, tz
        )
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
    unpainted = _choice(
        options.get("unpainted"),
        UNPAINTED,
        "photo" if widget in ("plate", "scene") else "silhouette",
    )
    only_painted = pictures == "paintings" and unpainted == "skip"
    # only painted aircraft: a single page looks among the nearest few for one already painted,
    # and keeps painting them, so a page has one most of the time
    pool = rows[: max(count, POOL) if only_painted else count]
    shown = pool
    if not shown:
        return {
            **base,
            "state": "empty",
            "hint": "Nothing within reach right now. A wider radius, or aircraft on the ground, would show more.",
        }

    # the unidentified contact, now and then
    ufo = (
        ufo_row(
            _int(options.get("ufo"), 0, 0, 100),
            subject_id(options),
            now,
            radius,
            options.get("visitors"),
        )
        if pictures == "paintings" and widget != "photo"
        else None
    )
    if ufo:
        shown = shown + [ufo] if widget == "cluster" else shown[:1] + [ufo]
    # routes, operators, photographs and marks: one aircraft's lookups beside the next's,
    # and none past the budget; a slow one finishes in the background for the next refresh
    deadline = fetch_started + BUDGET_S
    wants_photo = not only_painted and (
        pictures == "photos"
        or unpainted == "photo"
        or not fal_key
        or widget in ("photo", "plate", "scene")
    )

    def enrich(r: dict[str, Any]) -> dict[str, Any]:
        got: dict[str, Any] = {}
        got["route"] = A.route_of(r["cs"], data_dir, ua) if r["cs"] != r["reg"] else {}
        iata, air = A.airline_of(
            r["cs"], r["reg"], (got["route"] or {}).get("airline") or ""
        )
        got["iata"], got["air"] = iata, air
        got["photo"] = A.photo_of(r["reg"], data_dir, ua) if r["reg"] else {}
        if wants_photo and got["photo"].get("src"):
            N.cached_get(
                data_dir, got["photo"]["src"], ua=ua
            )  # the bytes, so the resize below is quick
        got["logo"] = (
            A.logo_src(iata, logo_source, data_dir, panel) if logos_on and iata else ""
        )
        got["brand"] = (
            A.brand_of(iata, logo_source, data_dir)
            if colours == "airline" and iata
            else {}
        )
        return got

    plain = [r for r in shown if not r.get("ufo")]
    deferred = 0
    if plain:
        pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="overhead-lookup")
        futures = {pool.submit(enrich, r): r for r in plain}
        done, pending = wait(futures, timeout=max(0.2, deadline - time.time()))
        pool.shutdown(wait=False)
        for f in done:
            r = futures[f]
            try:
                r.update(f.result())
            except Exception:
                logger.exception("overhead: lookups for %s failed", r.get("cs"))
                pending.add(f)
        for f in pending:
            r = futures[f]
            deferred += 1
            iata, air = A.airline_of(r["cs"], r["reg"], "")
            r.setdefault("route", {})
            r.setdefault("iata", iata)
            r.setdefault("air", air)
            r.setdefault("photo", {})
            r.setdefault("logo", "")
            r.setdefault("brand", {})
    # routes, operators, photographs
    for r in shown:
        if r.get("ufo"):
            r["lines"] = [
                "no transponder",
                f"{r['alt']:,} ft"
                + (
                    " climbing"
                    if r["rate"] > 0
                    else " descending"
                    if r["rate"] < 0
                    else ""
                ),
                f"{r['km']:g} km {compass(r['dir'])}",
            ]
            r["alt_text"], r["where"], r["trend"], r["route_text"] = (
                f"{r['alt']:,} ft",
                f"{r['km']:g} km {compass(r['dir'])}",
                "unknown",
                "no transponder",
            )
            r["about"] = (
                "An unidentified object with no transponder, no flight plan and no explanation."
            )
            r["sil"] = "/plugins/overhead_core/static/sil/ufo.svg"
            continue
        r["lines"] = lines_for(r, labels)
        r["alt_text"], r["where"], r["trend"], r["route_text"] = (
            alt_of(r),
            where_of(r),
            trend_of(r),
            route_text(r),
        )
        r["about"] = about_of(r)
        r["compass"] = compass(r["dir"])
        r["sil"] = f"/plugins/overhead_core/static/sil/{r['cls']}.svg"

    credits: list[str] = []
    px = (
        PHOTO_PX
        if widget in ("photo", "scene")
        else HERO_PX
        if widget == "plate"
        else PICTURE_PX
    )
    whole_ = backdrop != "none" or style in P.OWN_PAPER
    no_photo = 0
    for r in shown:
        photo = r.get("photo") or {}
        pic: dict[str, Any] | None = None
        if pictures == "paintings" and r.get("ufo"):
            key = P.ufo_key(r["ufo"], style)
            ref = P.ref_for(r["ufo"], P.own_refs(settings.get("visitor_refs")))
            payload = {
                "ufo": r["ufo"],
                "style": style,
                "how": how,
                "backdrop": "none",
                "model": paint_model,
                "photo": ref.get("src") or "",
                "by": ref.get("by") or "",
                "lic": ref.get("lic") or "",
                "link": f"https://commons.wikimedia.org/wiki/File:{ref['title']}"
                if ref
                else "",
                "aspect": "4:3",
            }
            got = art.request(key, payload, title=f"{r['typ']}, {P.style_of(style)[0]}")
            r["pic"] = (
                P.picture(art, key, px, panel, style in P.OWN_PAPER)
                if got.ready
                else None
            )
            continue
        if pictures == "paintings":
            key = P.key_for(
                r["reg"] or r["cs"], style, backdrop, view, model, sky, fidelity
            )
            payload = {
                "reg": r["reg"] or r["cs"],
                "typ": r["typ"],
                "air": r["air"] if r["air"] != "private" else "",
                "style": style,
                "how": how,
                "backdrop": backdrop,
                "sky_words": sky_words,
                "view": view,
                "fidelity": fidelity,
                "model": paint_model,
                "logo_ref": A.logo_ref(r.get("iata") or "", logo_source, data_dir)
                if r.get("iata")
                else "",
                "photo": photo.get("src") or "",
                "by": photo.get("by") or "",
                "link": photo.get("link") or "",
                "aspect": "4:3",
            }
            if photo.get(
                "src"
            ):  # nothing is asked for without a photograph to paint from
                got = art.request(
                    key, payload, title=f"{r['reg'] or r['cs']}, {r['typ']}"
                )
                if got.ready:
                    pic = P.picture(art, key, px, panel, whole_)
                    if pic and pic.get("credit"):
                        credits.append(pic["credit"])
                elif got.state == "failed":
                    r["why"] = got.why
            else:
                no_photo += 1
        # the photograph: asked for, or shown until the painting lands, or for want of a key
        if (
            pic is None
            and photo.get("src")
            and not only_painted
            and (
                pictures == "photos"
                or unpainted == "photo"
                or not fal_key
                or widget in ("photo", "plate", "scene")
            )
        ):
            src = (
                A.photo_src(photo, data_dir, ua, px, panel)
                if time.time() < deadline
                else ""
            )
            if not src and time.time() >= deadline:
                deferred += 1
            if src:
                pic = {
                    "src": src,
                    "kind": "photo",
                    "whole": True,
                    "credit": f"photo by {photo.get('by') or 'a planespotter'} (planespotters.net)",
                    "aspect": N.aspect_of(src),
                    "link": photo.get("link") or "",
                }
                credits.append(pic["credit"])
        r["pic"] = pic
        r.pop("lat", None)
        r.pop("lon", None)
    if widget != "cluster":
        contact = next((r for r in shown if r.get("ufo")), None)
        shown = [r for r in shown if not r.get("ufo")]
        if contact and contact.get("pic"):
            base["ufo"] = contact
    spent_mode = (
        _choice(options.get("when_spent"), SPENT, "keep")
        if widget == "cluster" and pictures == "paintings"
        else "keep"
    )
    kept_n = 0
    if spent_mode != "keep" and art.states.get("capped"):
        painted_now = [
            r for r in shown if r.get("pic") and r["pic"].get("kind") == "painting"
        ]
        gaps = [r for r in shown if r not in painted_now and not r.get("ufo")]
        kept = from_collection(
            art,
            data_dir,
            style=style,
            exclude={N.slug(r.get("reg") or r.get("cs") or "") for r in shown},
            n=min(len(gaps), count - len([r for r in painted_now if not r.get("ufo")])),
            mode=spent_mode,
            seed=subject_id(options),
            labels=labels,
            px=px,
            panel=panel,
            whole_=whole_,
            deadline=fetch_started + BUDGET_S + 1.0,
            now=now,
        )
        kept_n = len(kept)
        credits.extend(r["pic"]["credit"] for r in kept if r["pic"].get("credit"))
        shown = painted_now + kept + gaps[kept_n:]
        if kept_n:
            base["period"] = (
                f"{base['period']}, and {kept_n} from the collection"
                if painted_now
                else "from the collection"
            )
    if only_painted:
        painted_rows = [
            r for r in shown if r.get("pic") and r["pic"].get("kind") == "painting"
        ]
        shown = painted_rows[:count]
    elif widget == "cluster":
        shown = [
            r for r in shown if not r.get("ufo") or r.get("pic")
        ]  # an unpainted contact is no contact
    base["aircraft"] = shown
    base["shown"] = len(shown)

    notices, status = [], []
    if pictures == "paintings":
        status.extend(art.status())
        if kept_n:
            status.append(
                f"{kept_n} {'rare ones' if spent_mode == 'rare' else 'more'} from the collection while the budget is spent"
            )
        notices.extend(art.notes())
        if no_photo:
            status.append(f"{no_photo} without a photograph to paint from")
        art.finish(
            ctx, facet=style
        )  # a preview culls what it no longer wants; a panel records what it asked for
    if err:
        notices.append(err)
    if base.get("watch"):
        wv = base["watch"]
        status.insert(
            0,
            f"{wv['seen']} seen since {wv['since']}, {wv['present']} within reach now"
            if wv["seen"]
            else f"nothing seen since {wv['since']}",
        )
        if wv.get("error"):
            notices.append(f"the watch between renders: {wv['error']}")
    live = art.live()
    if deferred:
        status.append(f"{deferred} picture{'' if deferred == 1 else 's'} on the way")
        live["live_refresh_s"] = max(live["live_refresh_s"], LIVE_S)
    if only_painted and not shown:
        waiting = sum(art.states.get(k, 0) for k in ("painting", "waiting", "held"))
        base.update(
            state="painting",
            notices=notices,
            status=status,
            airborne=len(airborne),
            **live,
        )
        base["hint"] = (
            f"Painting {waiting} of the aircraft overhead; the page fills as they land."
            if waiting
            else P.NOTE_NO_KEY
            if art.states.get("no_key")
            else P.NEEDS_HOST
            if art.states.get("no_host")
            else "Nothing overhead is painted yet."
        )
        return base
    base.update(
        notices=notices,
        status=status,
        credits=list(dict.fromkeys(credits))[:4],
        airborne=len(airborne),
        attribution=f"positions from {feed or 'adsb.lol'}"
        if source == "adsb_lol"
        else "positions from your receiver",
        **live,
    )
    logger.info(
        "overhead: %s %s, %d near, %d shown, painted %d, started %d, held %d, no photo %d",
        "preview" if preview else "panel",
        widget,
        len(rows),
        len(shown),
        art.states.get("ready", 0),
        art.started,
        art.states.get("held", 0),
        no_photo,
    )
    return base
