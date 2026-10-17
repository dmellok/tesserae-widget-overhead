"""Overhead Core: the shared code for the four Overhead widgets, which load
lib/ by path, and a door to the paintings page Tesserae keeps for them
(``/plugins/overhead_core/artwork/paintings/``, Tesserae 0.463 and later)."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from flask import Blueprint, redirect

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


def blueprint() -> Any:
    """The Plugins menu's entry: it opens the paintings page Tesserae renders
    for the collection."""
    bp = Blueprint("overhead_core_admin", __name__, url_prefix="/plugins/overhead_core")

    @bp.get("/")
    def index() -> Any:
        return redirect(P.ART.href)

    return bp
