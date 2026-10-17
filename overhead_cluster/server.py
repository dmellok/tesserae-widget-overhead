"""Overhead: cluster. The work is in overhead_core/lib, loaded by path."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent / "overhead_core"
WIDGET = "cluster"


def _lib(name: str) -> Any:
    full = f"_tesserae_plugins.overhead_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _CORE / "lib" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Overhead Core is not installed beside this widget: install the Overhead bundle whole.")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def core_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """The Overhead Core settings (the key, the limits, the contact) from the
    host, with anything passed in on top (tests, or a widget of its own)."""
    core: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        from flask import current_app

        store = current_app.config.get("SETTINGS_STORE")
        manifest = _lib("net").read_json(_CORE / "plugin.json", {})
        fields = manifest.get("settings", []) if isinstance(manifest, dict) else []
        if store is not None:
            got = store.get_for_runtime("plugins", "overhead_core", fields)
            core = got if isinstance(got, dict) else {}
    extra = {k: v for k, v in (settings or {}).items() if v not in ("", None)}
    return {**core, **extra}


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    try:
        sheet = _lib("sheet")
    except RuntimeError as err:
        return {"error": str(err)}
    try:
        return sheet.fetch(dict(options or {}), core_settings(settings), dict(ctx or {}), WIDGET)
    except Exception as exc:  # noqa: BLE001 - the cell shows the words, not a traceback
        sheet.logger.exception("overhead: fetch failed")
        return {"error": f"Overhead could not load right now ({type(exc).__name__})."}
