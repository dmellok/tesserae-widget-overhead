"""The last aircraft seen at a place, for a page that would otherwise show an
empty sky.

Every fetch (and every poll of a watch between renders) hands ``note`` the
rows within reach. Each airframe is kept once, as the row it had when it came
closest, with when it was first and last seen; the newest KEEP of them stay,
none older than KEEP_S, in one small file per place under the core's data
folder. ``last`` hands them back newest first, each with seen_first,
seen_last and closest_at, the same fields a watched sighting carries, so the
page labels them the same way.

Unlike a watch this has no thread: it only knows what renders and watches
saw, so a page drawn every hour remembers the aircraft that were within
reach as it was drawn."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


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

KEEP = 48  # twice the most a page shows (sheet.MAX_COUNT)
KEEP_S = 7 * 86400
VISIT_GAP_S = 30 * 60  # seen again after this long is a new pass, kept afresh
# what a later sighting may fill in on the row kept at the closest approach
STATIC = ("cs", "typ", "cls", "reg", "span", "air", "op", "desc", "route")

_LOGS: dict[str, Log] = {}
_LOCK = threading.Lock()


class Log:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.seen: dict[str, dict[str, Any]] = {}
        got = N.read_json(path, None)
        if isinstance(got, dict) and isinstance(got.get("seen"), dict):
            self.seen = {
                k: v
                for k, v in got["seen"].items()
                if isinstance(v, dict) and isinstance(v.get("row"), dict)
            }

    def note(
        self,
        rows: Iterable[dict[str, Any]],
        id_of: Callable[[dict[str, Any]], str],
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        changed = False
        with self.lock:
            for r in rows:
                if r.get("visitor") or r.get("ufo"):
                    continue
                rid = str(id_of(r) or "").strip()
                if not rid:
                    continue
                km = float(r.get("km") or 0)
                e = self.seen.get(rid)
                if e is None or now - float(e.get("last") or 0) > VISIT_GAP_S:
                    self.seen[rid] = {
                        "first": now,
                        "last": now,
                        "km": km,
                        "at": now,
                        "row": _plain(r),
                    }
                else:
                    e["last"] = now
                    if km <= float(e.get("km") or 0):
                        e["km"], e["at"] = km, now
                        e["row"] = {**e["row"], **_plain(r)}
                    else:
                        row = e["row"]
                        for k in STATIC:
                            if r.get(k) and not row.get(k):
                                row[k] = r[k]
                changed = True
            if not changed:
                return
            cutoff = now - KEEP_S
            newest = sorted(
                (k for k, v in self.seen.items() if float(v.get("last") or 0) > cutoff),
                key=lambda k: -float(self.seen[k].get("last") or 0),
            )[:KEEP]
            self.seen = {k: self.seen[k] for k in newest}
            body = json.dumps({"seen": self.seen}, separators=(",", ":")).encode()
        with contextlib.suppress(Exception):
            N.write(self.path, body)

    def last(self, now: float | None = None) -> list[dict[str, Any]]:
        """The airframes kept, newest first, each as its closest row."""
        now = time.time() if now is None else now
        out = []
        with self.lock:
            for e in self.seen.values():
                last = float(e.get("last") or 0)
                if now - last > KEEP_S:
                    continue
                r = dict(e["row"])
                r["km"] = float(e.get("km") or r.get("km") or 0)
                r["seen_first"] = float(e.get("first") or last)
                r["seen_last"] = last
                r["closest_at"] = float(e.get("at") or last)
                r["age_s"] = int(max(0, now - last))
                out.append(r)
        out.sort(key=lambda r: -r["seen_last"])
        return out


def _plain(r: dict[str, Any]) -> dict[str, Any]:
    """The row as it can be written down: what a fetch added on top that does
    not survive JSON (or belongs to one render) is left off."""
    out = {}
    for k, v in r.items():
        if k in ("present", "closest_text", "seen_text"):
            continue
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


def log_for(data_dir: Path, lat: float, lon: float, radius: float) -> Log:
    key = f"{lat:.3f}|{lon:.3f}|{radius:g}"
    path = Path(data_dir) / "recent" / f"{N.slug(key)}.json"
    with _LOCK:
        got = _LOGS.get(str(path))
        if got is None:
            got = _LOGS[str(path)] = Log(path)
        return got
