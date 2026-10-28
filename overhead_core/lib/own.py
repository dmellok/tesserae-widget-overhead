"""Airframes painted on their own whatever a cell's One painting for says:
a special livery the fleet's painting would stand in for. One file under
the core's data folder, written from the paintings page (Paint a plane,
and the list beside it)."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path
from typing import Any

FILE = "own_airframes.json"
_LOCK = threading.Lock()


def normal(reg: str) -> str:
    """A registration as the list keeps it: upper case, no spaces."""
    return "".join(str(reg or "").split()).upper()


def load(data_dir: Path) -> dict[str, dict[str, Any]]:
    got = None
    with contextlib.suppress(OSError, ValueError, TypeError):
        got = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
    if not isinstance(got, dict):
        return {}
    return {
        normal(k): v for k, v in got.items() if isinstance(v, dict) and normal(k)
    }


def _save(data_dir: Path, items: dict[str, dict[str, Any]]) -> None:
    path = Path(data_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(items, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def regs(data_dir: Path) -> set[str]:
    """The registrations painted on their own."""
    return set(load(data_dir))


def listing(data_dir: Path) -> list[dict[str, Any]]:
    """The list for the page, newest first."""
    items = load(data_dir)
    return sorted(
        (
            {"reg": k, "note": str(v.get("note") or ""), "at": float(v.get("at") or 0)}
            for k, v in items.items()
        ),
        key=lambda e: -e["at"],
    )


def add(data_dir: Path, reg: str, note: str = "") -> str:
    """Keep the airframe on its own; returns the registration as kept, or ''."""
    key = normal(reg)
    if not key:
        return ""
    with _LOCK:
        items = load(data_dir)
        kept = items.get(key) or {}
        items[key] = {
            "note": " ".join(str(note or "").split())[:120] or str(kept.get("note") or ""),
            "at": float(kept.get("at") or time.time()),
        }
        _save(data_dir, items)
    return key


def remove(data_dir: Path, reg: str) -> bool:
    key = normal(reg)
    with _LOCK:
        items = load(data_dir)
        if key not in items:
            return False
        del items[key]
        _save(data_dir, items)
    return True
