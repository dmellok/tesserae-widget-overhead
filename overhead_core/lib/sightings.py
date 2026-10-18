"""How often each aircraft (ship, train) is seen, for how full the painted
catalogue is.

Every fetch, and every poll of a watch between renders, hands its rows to
``note``. A sighting is a pass: the same airframe seen again within
VISIT_GAP_S is the same pass, however many renders and cells caught it. The
ledger keeps, per airframe, when it was first and last seen and how many
passes, in one file under the core's data folder.

``stats`` turns the ledger into the numbers the paintings page shows: how
many airframes have been seen and how many passes; how many of them are
painted, and what share of the passes were of a painted one (the chance the
next one past is already in the catalogue); the Chao1 estimate of how many
airframes pass in all, from how many have been seen once and twice; and the
sample coverage (Good-Turing), the chance the next pass is an airframe seen
before. Loaded by path; the Overhead, Underway and Trackside cores carry the
same module."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

VISIT_GAP_S = 30 * 60  # seen again after this long is a new pass
SAVE_S = 60
KEEP_S = 365 * 86400
FILE = "sightings.json"

_LEDGERS: dict[str, Ledger] = {}
_LOCK = threading.Lock()


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.seen: dict[str, dict[str, Any]] = {}
        self.since = time.time()
        self.saved = 0.0
        self.dirty = False
        with contextlib.suppress(OSError, ValueError, TypeError):
            got = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(got, dict) and isinstance(got.get("seen"), dict):
                self.seen = {
                    k: v for k, v in got["seen"].items() if isinstance(v, dict)
                }
                self.since = float(got.get("since") or self.since)

    def note(
        self,
        rows: Iterable[dict[str, Any]],
        id_of: Callable[[dict[str, Any]], str],
        name_of: Callable[[dict[str, Any]], str],
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self.lock:
            for r in rows:
                if r.get("visitor") or r.get("ufo"):
                    continue
                rid = str(id_of(r) or "").strip()
                if not rid:
                    continue
                e = self.seen.get(rid)
                if e is None:
                    self.seen[rid] = {"f": now, "l": now, "v": 1, "n": name_of(r)}
                elif now - float(e.get("l") or 0) > VISIT_GAP_S:
                    e["v"] = int(e.get("v") or 0) + 1
                    e["l"] = now
                    e["n"] = name_of(r) or e.get("n") or ""
                else:
                    e["l"] = now
                self.dirty = True
            due = self.dirty and now - self.saved > SAVE_S
        if due:
            self.save(now)

    def save(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.lock:
            cutoff = now - KEEP_S
            keep = {
                k: v for k, v in self.seen.items() if float(v.get("l") or 0) > cutoff
            }
            body = json.dumps(
                {"since": self.since, "seen": keep}, separators=(",", ":")
            )
            self.saved, self.dirty = now, False
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.name}.tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(self.path)


def ledger(data_dir: Path) -> Ledger:
    path = Path(data_dir) / FILE
    with _LOCK:
        got = _LEDGERS.get(str(path))
        if got is None:
            got = _LEDGERS[str(path)] = Ledger(path)
        return got


def painted_prefixes(folder: Path) -> set[str]:
    """The subjects with a painting kept: the first part of each painting's key."""
    out: set[str] = set()
    with contextlib.suppress(OSError):
        for p in Path(folder).iterdir():
            if (
                p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                and "--" in p.stem
            ):
                out.add(p.stem.split("--", 1)[0])
    return out


def stats(
    data_dir: Path,
    is_painted: Callable[[str], bool],
    now: float | None = None,
    top: int = 12,
) -> dict[str, Any]:
    """The numbers for the paintings page (see the module's docstring)."""
    now = time.time() if now is None else now
    led = ledger(data_dir)
    with led.lock:
        seen = {k: dict(v) for k, v in led.seen.items()}
        since = led.since
    n_air = len(seen)
    passes = sum(int(v.get("v") or 1) for v in seen.values())
    f1 = sum(1 for v in seen.values() if int(v.get("v") or 1) == 1)
    f2 = sum(1 for v in seen.values() if int(v.get("v") or 1) == 2)
    chao1 = n_air + (f1 * f1 / (2 * f2) if f2 else f1 * (f1 - 1) / 2) if n_air else 0
    painted = {k for k in seen if is_painted(k)}
    painted_passes = sum(int(seen[k].get("v") or 1) for k in painted)
    week = now - 7 * 86400
    new_week = sum(1 for v in seen.values() if float(v.get("f") or 0) > week)
    days = max(1.0, (now - since) / 86400)
    coverage = 1 - f1 / passes if passes else 0.0
    rows = sorted(
        seen.items(),
        key=lambda kv: (-int(kv[1].get("v") or 1), -float(kv[1].get("l") or 0)),
    )[:top]
    return {
        "airframes": n_air,
        "passes": passes,
        "once": f1,
        "twice": f2,
        "estimate": round(chao1),
        "seen_share": round(n_air / chao1, 3) if chao1 else 0.0,
        "coverage": round(coverage, 3),
        "painted": len(painted),
        "painted_share": round(len(painted) / n_air, 3) if n_air else 0.0,
        "painted_passes_share": round(painted_passes / passes, 3) if passes else 0.0,
        "next_painted": round(coverage * painted_passes / passes, 3) if passes else 0.0,
        "new_week": new_week,
        "days": round(days, 1),
        "since": since,
        "top": [
            {
                "id": k,
                "name": v.get("n") or "",
                "passes": int(v.get("v") or 1),
                "last": float(v.get("l") or 0),
                "painted": k in painted,
            }
            for k, v in rows
        ],
    }
