"""Overhead Core: the shared code for the four Overhead widgets, which load
lib/ by path, and a door to the paintings page Tesserae keeps for them
(``/plugins/overhead_core/artwork/paintings/``, Tesserae 0.463 and later)."""

from __future__ import annotations

import contextlib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, flash, redirect, request

_HERE = Path(__file__).resolve().parent


def lib(name: str) -> Any:
    full = f"_tesserae_plugins.overhead_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / "lib" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


N = lib("net")
P = lib("paint")
S = lib("sheet")
SG = lib("sightings")
A = lib("adsb")
OWN = lib("own")
REG_RE = re.compile(r"[A-Z0-9]{1,6}(-[A-Z0-9]{1,6})?")


def page_context(data_dir: Path) -> dict[str, Any]:
    """What the paintings page shows beside the gallery: the catalogue's
    numbers, the Paint a plane form's choices (every airframe the widgets
    have seen, the styles, the models) and the airframes kept on their own."""
    led = SG.ledger(data_dir)
    with led.lock:
        known = sorted(
            (k, str(v.get("n") or k)) for k, v in led.seen.items() if k
        )
    return {
        **sightings_context(data_dir),
        "known": known,
        "own": OWN.listing(data_dir),
        "styles": [(k, v[0]) for k, v in P.STYLES.items() if k not in P.HIDDEN]
        + [("custom", "Your own prompt")],
        "models": [(k, f"{v['label']} ({v['cost']})") for k, v in P.MODELS.items()],
    }


def sightings_context(data_dir: Path) -> dict[str, Any]:
    """The catalogue's numbers for the paintings page: a pass is painted when
    a painting's key begins with its id, as every painting of it does, or with
    the fleet or the type its painting stands for (its type in its operator's
    colours, the group the ledger tagged it with)."""
    painted = SG.painted_prefixes(P.gen_dir(data_dir))

    def is_painted(rid: str) -> bool:
        return any(N.slug(x) in painted for x in (rid, f"fleet {rid}", f"type {rid}"))

    return {"s": SG.stats(data_dir, is_painted)}


P.ART.extra_template = "overhead_core/sightings.html"
P.ART.extra_context = page_context


def settings_of(settings_store: Any) -> dict[str, Any]:
    """The core's settings from the host's store, or {}."""
    if settings_store is None:
        return {}
    manifest = N.read_json(_HERE / "plugin.json", {})
    fields = manifest.get("settings", []) if isinstance(manifest, dict) else []
    with contextlib.suppress(Exception):
        got = settings_store.get_for_runtime("plugins", "overhead_core", fields)
        return got if isinstance(got, dict) else {}
    return {}


def _fal_key(settings: dict[str, Any]) -> str:
    try:
        from app import fal

        return str(fal.resolve_key(settings) or "")
    except Exception:  # noqa: BLE001 - outside the host: the core's own setting
        return str(settings.get("fal_api_key") or "")


def blueprint() -> Any:
    """The Plugins menu's entry opens the paintings page Tesserae renders
    for the collection; beside it, the page's own forms: an airframe painted
    by its registration (Paint a plane), and the list of airframes kept on
    their own whatever a cell's One painting for says."""
    bp = Blueprint(
        "overhead_core_admin",
        __name__,
        url_prefix="/plugins/overhead_core",
        template_folder="templates",
    )

    def plugin() -> Any:
        registry = current_app.config["PLUGIN_REGISTRY"]
        for pl in registry.plugins.values():
            with contextlib.suppress(OSError, AttributeError):
                if Path(pl.path).resolve() == _HERE:
                    return pl
        abort(404)

    def data_dir() -> Path:
        path = Path(plugin().data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def settings() -> dict[str, Any]:
        return settings_of(current_app.config.get("SETTINGS_STORE"))

    def back() -> Any:
        return redirect(P.ART.href)

    def start(dd: Path, st: dict[str, Any], key: str, payload: dict[str, Any], label: str) -> tuple[str, str]:
        """One painting started: (what to say, how) for a flash."""
        fal_key = _fal_key(st)
        cap = P.ART.cap(st)
        if not fal_key:
            return "Add a fal.ai key in the Overhead Core settings first.", "warn"
        if cap < P.UNLIMITED and P.ART.budget_used(dd) >= cap:
            return (
                f"To-day's painting budget of {P.dollars(cap)} is spent. Raise it in the Overhead Core settings.",
                "warn",
            )
        if P.ART.path(key, dd) is not None:
            return f"{label} is painted already; use Repaint on its card for another version.", "info"
        if not P.ART.start(P.ART.job(key, payload, label, dd, fal_key), cap):
            return f"{label} is already being painted.", "info"
        P.ART.clear_error(key, dd)
        return f"Painting {label}. It takes up to a minute; the page redraws when it lands.", "success"

    def paint_airframe(
        dd: Path,
        st: dict[str, Any],
        reg: str,
        *,
        typ: str = "",
        air: str = "",
        style: str = "poster",
        how: str = "",
        model: str = "",
        own: bool = False,
        note: str = "",
    ) -> tuple[str, str]:
        """An airframe painted by its registration, from its photograph on
        planespotters.net, as the cluster and a plain plate show it: alone on
        the paper, as photographed. Its type and operator as given, else
        adsbdb, else what the widgets saw it as; kept on its own when asked."""
        ua = A.user_agent(str(st.get("contact") or ""))
        if own:
            OWN.add(dd, reg, note)
        photo = A.photo_of(reg, dd, ua)
        if not photo.get("src"):
            return (
                f"planespotters.net has no photograph of {reg}, so there is nothing to paint it from."
                + (" It is kept on its own all the same." if own else ""),
                "warn",
            )
        found = A.airframe_of(reg, dd, ua)
        seen = SG.ledger(dd).seen.get(reg) or {}
        seen_typ = str(seen.get("n") or "").partition(" · ")[2]
        typ = typ or found.get("typ") or seen_typ
        code = found.get("code") or next(
            (k for k, v in A.TYPES.items() if typ and v[0].lower() == typ.lower()), ""
        )
        cls = "jet"
        if code:
            name, cls, _span = A.type_of(code)
            typ = typ or name
        typ = typ or "aircraft"
        air = air or found.get("owner") or ""
        if style == "custom":
            how = how or P.CUSTOM_EXAMPLE
            style = P.register_custom(how)
        elif style not in P.STYLES:
            style = "poster"
        model = P.model_of(model)
        gear = A.gear_of(cls, code)
        key = P.key_for(reg, style, "none", "side", model, "", "photo", gear)
        payload = {
            "gear": gear,
            "reg": reg,
            "from_reg": reg,
            "fleet": "",
            "typ": typ,
            "air": air,
            "style": style,
            "how": how,
            "backdrop": "none",
            "sky_words": "",
            "view": "side",
            "fidelity": "photo",
            "model": P.model_for(style, model),
            "logo_ref": "",
            "photo": photo.get("src") or "",
            "by": photo.get("by") or "",
            "link": photo.get("link") or "",
            "aspect": "4:3",
        }
        return start(dd, st, key, payload, f"{reg}, {typ}")

    def paint_on_its_own(key: str, dd: Path) -> str:
        """A fleet painting's card: the airframe it was painted from set on
        its own and painted by its registration, so the fleet's painting
        stands for the rest and this one shows as itself."""
        meta = P.ART.meta(key, dd)
        reg = OWN.normal(str(meta.get("from_reg") or meta.get("reg") or ""))
        if not meta.get("fleet"):
            return f"{reg or key} is painted on its own already."
        if not reg:
            return (
                "This fleet painting was made before the registration it came from was kept; "
                "use Paint a plane with the registration instead."
            )
        msg, _how = paint_airframe(
            dd,
            settings(),
            reg,
            typ=str(meta.get("typ") or ""),
            air=str(meta.get("air") or ""),
            style=str(meta.get("style") or "poster"),
            how=str(meta.get("how") or ""),
            model=str(meta.get("model") or ""),
            own=True,
            note="from its fleet's card",
        )
        return f"{reg} always gets its own painting now, even in a cell set to one painting per fleet. {msg}"

    if hasattr(P.ART, "action") and not any(s == "own" for s, _l, _f in P.ART.actions):
        P.ART.action("own", "Paint on its own", paint_on_its_own)

    @bp.get("/")
    def index() -> Any:
        return back()

    @bp.post("/paint")
    def paint() -> Any:
        """An airframe painted by its registration, from its photograph on
        planespotters.net, as the cluster and a plain plate show it: alone on
        the paper, as photographed. Its type and operator from the form, else
        adsbdb, else what the widgets saw it as; kept on its own when asked."""
        reg = OWN.normal(request.form.get("reg"))
        if not REG_RE.fullmatch(reg):
            flash("Give a registration, for example VH-XZP.", "warn")
            return back()
        msg, how = paint_airframe(
            data_dir(),
            settings(),
            reg,
            typ=" ".join(request.form.get("typ", "").split())[:60],
            air=" ".join(request.form.get("air", "").split())[:60],
            style=str(request.form.get("style") or "poster"),
            how=" ".join(request.form.get("how", "").split())[:600],
            model=str(request.form.get("model") or ""),
            own=request.form.get("own") == "1",
            note=request.form.get("note", ""),
        )
        flash(msg, how)
        return back()

    @bp.post("/own/add")
    def own_add() -> Any:
        reg = OWN.normal(request.form.get("reg"))
        if not REG_RE.fullmatch(reg):
            flash("Give a registration, for example VH-XZP.", "warn")
        else:
            OWN.add(data_dir(), reg, request.form.get("note", ""))
            flash(
                f"{reg} always gets its own painting now, even in a cell set to one painting per fleet.",
                "success",
            )
        return back()

    @bp.post("/own/remove")
    def own_remove() -> Any:
        reg = OWN.normal(request.form.get("reg"))
        if OWN.remove(data_dir(), reg):
            flash(f"{reg} goes with its fleet again.", "success")
        return back()

    return bp
