"""Overhead Core: the paintings page and the shared code for the four
Overhead widgets, which load lib/ by path."""

from __future__ import annotations

import contextlib
import importlib.util
import re
import sys
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

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

_KEY_RE = re.compile(r"[a-z0-9_]{1,60}(?:--[a-z0-9_]{1,24}){0,6}")
_ARCHIVED_RE = re.compile(r"([a-z0-9_]{1,60}(?:--[a-z0-9_]{1,24}){0,6})__(\d{8}-\d{6})")


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


def gallery(data_dir: Path, cap: int) -> dict[str, Any]:
    folder = P.gen_dir(data_dir)
    entries: dict[str, dict[str, Any]] = {}

    def entry(key: str) -> dict[str, Any]:
        parts = key.split("--")
        return entries.setdefault(key, {"key": key, "reg": parts[0].replace("_", "-").upper(), "style": parts[1] if len(parts) > 1 else "poster", "style_label": P.style_of(parts[1] if len(parts) > 1 else "poster")[0], "backdrop": next((p[3:] for p in parts[2:] if p.startswith("bd_")), "none"), "typ": "", "air": "", "active": None, "archive": [], "error": "", "painting": False})

    for f in sorted(folder.glob("*.jpg")):
        key = f.stem
        if not _KEY_RE.fullmatch(key) or "_cut" in key or re.search(r"_\d+$", key):
            continue
        meta = N.read_json(folder / f"{key}.json", {})
        meta = meta if isinstance(meta, dict) else {}
        e = entry(key)
        air = str(meta.get("air") or "")
        e.update(active={"file": f.name, "made": time.strftime("%-d %b %Y" if sys.platform != "win32" else "%d %b %Y", time.localtime(f.stat().st_mtime))}, typ=str(meta.get("typ") or ""), air="" if air in ("private", "its operator's", "its own") else air, reg=str(meta.get("reg") or e["reg"]), credit=str(meta.get("credit") or ""), photo_link=str(meta.get("photo_link") or ""), photo_by=str(meta.get("photo_by") or ""), model=str(meta.get("model") or ""))
    for f in sorted(folder.glob("*.err")):
        key = f.stem
        if _KEY_RE.fullmatch(key):
            why = P.why_failed(key, folder)
            if why and P.state(key, folder) == "failed":
                entry(key)["error"] = why
    arch = folder / "archive"
    if arch.is_dir():
        for f in sorted(arch.glob("*.jpg"), reverse=True):
            m = _ARCHIVED_RE.fullmatch(f.stem)
            if m:
                entry(m.group(1))["archive"].append({"file": f.name, "made": m.group(2)[:8]})
    with P._LOCK:
        running = set(P._PAINTING)
    for key, e in entries.items():
        e["painting"] = key in running
    ordered = sorted(entries.values(), key=lambda e: (e["active"] is None, e["reg"], e["style"]))
    groups: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    placed: set[str] = set()
    now = time.time()
    for d in S.dashboards(data_dir):
        have = [entries[k] for k in d.get("keys", []) if k in entries]
        missing = len([k for k in d.get("keys", []) if k not in entries or not entries[k]["active"]])
        if not have and not missing:
            continue
        placed.update(e["key"] for e in have)
        grp = by_name.get(d.get("name") or "")
        if grp is None:
            grp = {"name": d.get("name") or "", "icon": d.get("icon") or "", "tabs": []}
            by_name[grp["name"]] = grp
            groups.append(grp)
        grp["tabs"].append({"id": d["id"], "style_label": d.get("style_label") or "", "paintings": have, "missing": missing, "on_panel": now - float(d.get("at") or 0) <= S.ON_FRAME_S})
    rest = [e for e in ordered if e["key"] not in placed]
    return {"paintings": ordered, "groups": groups, "rest": rest, "used": P.budget_used(folder), "cap": cap, "used_text": P.dollars(P.budget_used(folder)), "cap_text": P.dollars(cap), "styles": [(k, v[0]) for k, v in P.STYLES.items()]}


def purge_all(data_dir: Path) -> dict[str, int]:
    P.stop_all(data_dir)
    folder = P.gen_dir(data_dir)
    out = {"paintings": 0, "versions": 0}
    with contextlib.suppress(OSError):
        for f in folder.iterdir():
            if f.is_file() and f.name != "budget.json":
                if f.suffix == ".jpg" and "_cut" not in f.stem and not re.search(r"_\d+$", f.stem):
                    out["paintings"] += 1
                f.unlink()
        arch = folder / "archive"
        if arch.is_dir():
            for f in arch.iterdir():
                if f.suffix == ".jpg":
                    out["versions"] += 1
                f.unlink()
    S._unhold(data_dir)
    S.T.waiting_over(0)
    return out


def blueprint() -> Any:
    from flask import current_app

    bp = Blueprint("overhead_core_admin", __name__, template_folder="templates")

    def data_dir() -> Path:
        reg = current_app.config.get("PLUGIN_REGISTRY")
        pl = reg.plugins.get("overhead_core") if reg is not None else None
        root = Path(getattr(pl, "data_dir", None) or Path(current_app.config.get("DATA_ROOT", ".")) / "plugins" / "overhead_core")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def settings() -> dict[str, Any]:
        return settings_of(current_app.config.get("SETTINGS_STORE"))

    def fal_key() -> str:
        return str(settings().get("fal_api_key") or "").strip()

    def cap() -> int:
        P.configure(settings())
        return P.daily_cap(settings())

    def back() -> Any:
        return redirect(url_for("overhead_core_admin.index"))

    def key_or_404(key: str) -> str:
        if not _KEY_RE.fullmatch(key):
            abort(404)
        return key

    @bp.get("/")
    def index() -> str:
        dd = data_dir()
        return render_template("overhead_core/admin.html", g=gallery(dd, cap()), has_key=bool(fal_key()), held=len(S.held(dd)), wanted=len(S.dashboards(dd)), contact=bool(str(settings().get("contact") or "").strip()))

    @bp.get("/progress")
    def progress() -> Any:
        return jsonify(P.progress(P.gen_dir(data_dir()), cap(), bool(fal_key())))

    @bp.post("/stop")
    def stop_one() -> Any:
        key = key_or_404(request.form.get("key", ""))
        P.stop(key, data_dir())
        return jsonify({"ok": True}) if request.accept_mimetypes.best == "application/json" else back()

    @bp.post("/stop-all")
    def stop_all() -> Any:
        n = P.stop_all(data_dir())
        return jsonify({"stopped": n}) if request.accept_mimetypes.best == "application/json" else back()

    @bp.get("/painting/<path:name>")
    def image(name: str) -> Any:
        folder = P.gen_dir(data_dir())
        if name.startswith("archive/"):
            stem = name[8:-4]
            if not name.endswith(".jpg") or not _ARCHIVED_RE.fullmatch(stem):
                abort(404)
            path = folder / "archive" / f"{stem}.jpg"
        else:
            if not name.endswith(".jpg") or not _KEY_RE.fullmatch(name[:-4]):
                abort(404)
            path = folder / name
        if not path.exists():
            abort(404)
        return send_file(path, mimetype="image/jpeg", max_age=3600)

    @bp.post("/render-now")
    def render_now_route() -> Any:
        key = fal_key()
        if not key:
            flash("Add a fal.ai key in the Overhead Core settings first.", "warn")
            return back()
        n, found = S.render_now(data_dir(), key, cap(), request.form.get("who", ""))
        if not found:
            flash("Nothing is missing: every painting the panels ask for is there. A page that has not rendered to a panel yet asks for nothing here.", "info")
        elif not n:
            flash(f"To-day's painting budget of {P.dollars(cap())} is spent, or those are already being painted.", "warn")
        else:
            flash(f"Painting {n} aircraft. Watch the job tray at the bottom right.", "success")
        return back()

    @bp.post("/paint-held")
    def paint_held() -> Any:
        key = fal_key()
        if not key:
            flash("Add a fal.ai key in the Overhead Core settings first.", "warn")
            return back()
        n = S.start_held(data_dir(), key, cap())
        flash(f"Painting {n} held painting{'' if n == 1 else 's'}." if n else "Nothing is waiting, or to-day's limit is used up.", "success" if n else "info")
        return back()

    @bp.post("/purge")
    def purge() -> Any:
        got = purge_all(data_dir())
        flash(f"Gone: {got['paintings']} painting{'' if got['paintings'] == 1 else 's'} and {got['versions']} earlier version{'' if got['versions'] == 1 else 's'}.", "success")
        return back()

    @bp.post("/budget-reset")
    def budget_reset() -> Any:
        N.write(P.gen_dir(data_dir()) / "budget.json", b"{}")
        flash("To-day's count is 0 again.", "success")
        return back()

    @bp.post("/<key>/repaint")
    def repaint(key: str) -> Any:
        key = key_or_404(key)
        dd = data_dir()
        folder = P.gen_dir(dd)
        meta = N.read_json(folder / f"{key}.json", {})
        job = {k: meta.get(k) for k in ("reg", "typ", "air", "style", "how", "backdrop", "model")} if isinstance(meta, dict) else {}
        photo = S.A.photo_of(str(job.get("reg") or ""), dd, S.A.user_agent(str(settings().get("contact") or "")))
        if not photo.get("src"):
            flash("No photograph of this airframe to paint from.", "warn")
            return back()
        job.update(key=key, photo=photo["src"], by=photo.get("by", ""), link=photo.get("link", ""), aspect="4:3", origin="panel")
        if job.get("style") and str(job["style"]).startswith("custom") and job.get("how"):
            P._CUSTOM[str(job["style"])] = str(job["how"])
        P.archive(folder, key)
        with contextlib.suppress(OSError):
            (folder / f"{key}.err").unlink()
        if not P.start(job, dd, fal_key(), cap()):
            flash("That one is already being painted.", "info")
        else:
            flash(f"Painting {job.get('reg')} again; the earlier version is kept.", "success")
        return back()

    @bp.post("/<key>/delete")
    def delete(key: str) -> Any:
        key = key_or_404(key)
        folder = P.gen_dir(data_dir())
        P.archive(folder, key)
        with contextlib.suppress(OSError):
            (folder / f"{key}.err").unlink()
        flash("Moved to the earlier versions; painted again when a page asks for it.", "success")
        return back()

    @bp.post("/<key>/clear-error")
    def clear_error(key: str) -> Any:
        key = key_or_404(key)
        with contextlib.suppress(OSError):
            (P.gen_dir(data_dir()) / f"{key}.err").unlink()
        return back()

    @bp.post("/archive/<stem>/use")
    def use_archived(stem: str) -> Any:
        m = _ARCHIVED_RE.fullmatch(stem)
        if not m:
            abort(404)
        folder = P.gen_dir(data_dir())
        key = m.group(1)
        if (folder / f"{key}.jpg").exists():
            P.archive(folder, key)
        import os

        for ext in (".jpg", ".json"):
            with contextlib.suppress(OSError):
                os.replace(folder / "archive" / f"{stem}{ext}", folder / f"{key}{ext}")
        P.drop_derived(folder, key)
        flash("That version is current again.", "success")
        return back()

    @bp.post("/archive/<stem>/delete")
    def delete_archived(stem: str) -> Any:
        if not _ARCHIVED_RE.fullmatch(stem):
            abort(404)
        folder = P.gen_dir(data_dir())
        for ext in (".jpg", ".json"):
            with contextlib.suppress(OSError):
                (folder / "archive" / f"{stem}{ext}").unlink()
        return back()

    return bp
