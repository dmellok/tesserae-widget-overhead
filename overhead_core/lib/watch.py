"""A watch on a place between renders: everything that passed since the page
was last drawn.

A panel draws a page every half hour or hour, and what is within reach at
that moment is one moment of the traffic. A watch samples the place on its
own thread while a page asks (and for KEEP_S after the last ask), remembers
every object it sees with the moment it came closest, and hands a render
everything seen since the previous render's window began. The windows chain:
each render that advances the mark starts its window where the last advance
was made, so nothing falls between two pages, and renders closer together
than MIN_WINDOW_S (a warm-ahead, the settle and the send of one page) share
one window rather than each starting a new one. A preview never advances
the mark. Loaded by path; the Underway and Overhead cores carry the same
module."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("tesserae.plugins.watch")
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

KEEP_S = 3 * 3600  # a watch no page has asked for stops after this
SAVE_S = 30
SEEN_S = 48 * 3600  # a sighting is remembered this long
SEEN_MAX = 3000
MIN_WINDOW_S = 10 * 60  # renders closer together than this share one window
FIRST_WINDOW_S = 3600  # a page's first render: the last hour
# what a later sighting may fill in on the record kept at the closest approach
STATIC = (
    "name",
    "cs",
    "imo",
    "dest",
    "eta",
    "len",
    "beam",
    "draught",
    "typ",
    "cls",
    "code",
    "flag",
    "flag_cc",
    "reg",
    "span",
)


class Watch:
    """One sampler for one place: ``poll`` is asked every ``every_s`` for the
    rows within reach, ``id_of`` names a row, and ``seen`` keeps each object
    once with the row it had when it came closest."""

    def __init__(
        self,
        key: str,
        poll: Callable[[], list[dict[str, Any]]],
        every_s: float,
        path: Path,
        id_of: Callable[[dict[str, Any]], str],
    ) -> None:
        self.key, self.poll, self.every_s, self.path, self.id_of = (
            key,
            poll,
            every_s,
            path,
            id_of,
        )
        self.seen: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.until = time.time() + KEEP_S
        self.polls = 0
        self.error = ""
        self._dirty = False
        got = N.read_json(path, None)
        if isinstance(got, dict) and isinstance(got.get("seen"), dict):
            cutoff = time.time() - SEEN_S
            self.seen = {
                k: v
                for k, v in got["seen"].items()
                if isinstance(v, dict)
                and isinstance(v.get("row"), dict)
                and float(v.get("last") or 0) > cutoff
            }
        self.thread = threading.Thread(target=self._run, name="watch", daemon=True)
        self.thread.start()

    def ask(self) -> None:
        self.until = time.time() + KEEP_S

    # -- the thread ---------------------------------------------------------

    def _run(self) -> None:
        last_save = 0.0
        while not self.stop.is_set() and time.time() < self.until:
            try:
                rows = self.poll()
                self.error = ""
            except Exception as err:  # noqa: BLE001 - the watch keeps watching whatever one poll did
                self.error = f"{type(err).__name__}: {str(err)[:120]}"
                logger.warning("watch %s: %s", self.key, self.error)
                rows = []
            self.polls += 1
            if rows:
                self.note(rows)
            if self._dirty and time.time() - last_save > SAVE_S:
                last_save = time.time()
                self.save()
            if self.stop.wait(self.every_s):
                break
        self.save()
        with _WATCHES_LOCK:
            if _WATCHES.get(self.key) is self:
                _WATCHES.pop(self.key, None)

    # -- what a fetch does with it ------------------------------------------

    def note(self, rows: list[dict[str, Any]], now: float | None = None) -> None:
        """Rows within reach at ``now``: a new object is kept as it is, one seen
        before is kept at its closest approach, and what it has since said of
        itself fills in."""
        now = time.time() if now is None else now
        with self.lock:
            for r in rows:
                rid = self.id_of(r)
                if not rid or r.get("visitor") or r.get("ufo"):
                    continue
                km = float(r.get("km") or 0)
                e = self.seen.get(rid)
                if e is None:
                    self.seen[rid] = {
                        "first": now,
                        "last": now,
                        "n": 1,
                        "km": km,
                        "at": now,
                        "row": dict(r),
                    }
                    continue
                e["last"] = now
                e["n"] = int(e.get("n") or 0) + 1
                if km <= float(e.get("km") or 0):
                    e["km"], e["at"] = km, now
                    e["row"] = {**e["row"], **r}
                else:
                    row = e["row"]
                    for k in STATIC:
                        if r.get(k) and not row.get(k):
                            row[k] = r[k]
            if len(self.seen) > SEEN_MAX:
                for rid in sorted(self.seen, key=lambda k: self.seen[k]["last"])[
                    : len(self.seen) - SEEN_MAX
                ]:
                    self.seen.pop(rid, None)
            self._dirty = True

    def since(self, t0: float, now: float | None = None) -> list[dict[str, Any]]:
        """Everything seen since ``t0``, each as the row it had when closest,
        with seen_first, seen_last, seen_n and closest_at."""
        now = time.time() if now is None else now
        out = []
        with self.lock:
            for e in self.seen.values():
                if float(e.get("last") or 0) < t0:
                    continue
                r = dict(e["row"])
                r["km"] = float(e.get("km") or r.get("km") or 0)
                r["seen_first"] = float(e.get("first") or 0)
                r["seen_last"] = float(e.get("last") or 0)
                r["seen_n"] = int(e.get("n") or 1)
                r["closest_at"] = float(e.get("at") or r["seen_last"])
                r["age_s"] = int(max(0, now - r["seen_last"]))
                out.append(r)
        out.sort(key=lambda r: (r["km"], -r["seen_last"]))
        return out

    def save(self) -> None:
        with self.lock:
            cutoff = time.time() - SEEN_S
            keep = {
                k: v for k, v in self.seen.items() if float(v.get("last") or 0) > cutoff
            }
            self._dirty = False
        with contextlib.suppress(Exception):
            N.write(
                self.path,
                json.dumps({"at": time.time(), "key": self.key, "seen": keep}).encode(),
            )


_WATCHES: dict[str, Watch] = {}
_WATCHES_LOCK = threading.Lock()


def watch_for(
    key: str,
    poll: Callable[[], list[dict[str, Any]]],
    every_s: float,
    data_dir: Path,
    id_of: Callable[[dict[str, Any]], str],
) -> Watch:
    """The watch on a place, started if there is none, kept for KEEP_S more."""
    with _WATCHES_LOCK:
        got = _WATCHES.get(key)
        if got is None or not got.thread.is_alive():
            got = Watch(
                key, poll, every_s, data_dir / "watch" / f"{N.slug(key)}.json", id_of
            )
            _WATCHES[key] = got
        got.ask()
        return got


def stop_watches() -> None:
    with _WATCHES_LOCK:
        for w in list(_WATCHES.values()):
            w.stop.set()
        _WATCHES.clear()


# ----------------------------------------------------------------------
# The window a render shows
# ----------------------------------------------------------------------
def window(data_dir: Path, subject: str, now: float, advance: bool) -> float:
    """When a cell's window begins. A render that advances the mark (a panel's
    own, not a preview) starts its window where the last advance was made;
    one within MIN_WINDOW_S of the last advance shows the same window, so the
    warm-ahead, the settle and the send of one page agree. The first render
    shows the last hour."""
    path = data_dir / "watch" / "marks.json"
    marks = N.read_json(path, None)
    marks = marks if isinstance(marks, dict) else {}
    m = marks.get(subject)
    m = m if isinstance(m, dict) else {}
    start = float(m.get("start") or 0)
    marked = float(m.get("marked") or 0)
    if not marked:
        start = marked = now - FIRST_WINDOW_S
        if advance:
            marked = now
    elif advance and now - marked >= MIN_WINDOW_S:
        start, marked = marked, now
    if advance:
        marks[subject] = {"start": start, "marked": marked}
        cutoff = now - 30 * 86400
        marks = {
            k: v
            for k, v in marks.items()
            if isinstance(v, dict) and float(v.get("marked") or 0) > cutoff
        }
        with contextlib.suppress(Exception):
            N.write(path, json.dumps(marks).encode())
    return start


def clock(ts: float, tz: Any) -> str:
    """A time of day for the page, in the page's zone."""
    from datetime import datetime

    try:
        d = (
            datetime.fromtimestamp(ts, tz)
            if tz
            else datetime.fromtimestamp(ts).astimezone()
        )
    except (OverflowError, OSError, ValueError):
        return ""
    return d.strftime("%H:%M")
