"""Progress of the paintings and cut-outs, shown in Tesserae's job tray.

Tesserae (0.454 and later) draws a card for anything that reports to
``app.jobs``. A batch here is "everything queued since the queue was last
empty": the card counts the finished against the whole and closes when the
last one is done. On an older Tesserae the import fails and nothing happens.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

try:
    from app import jobs
except ImportError:  # an older Tesserae, or a test without the app
    jobs = None

SOURCE = "overhead"
LABEL = "Overhead"
HREF = "/plugins/overhead_core/"


class Batch:
    def __init__(self, key: str, title: str) -> None:
        self.key = key
        self.title = title
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._total = 0
        self._stopped = 0
        self._stop: Callable[[], object] | None = None

    def add(self, item: str, stop: Callable[[], object]) -> None:
        with self._lock:
            if not self._pending:
                self._total = 0
                self._stopped = 0
            if item in self._pending:
                return
            self._pending.add(item)
            self._total += 1
            self._stop = stop
            self._push()

    def done(self, item: str, stopped: bool = False) -> None:
        """One item is over. Safe to call twice for the same item."""
        with self._lock:
            if item not in self._pending:
                return
            self._pending.discard(item)
            if stopped:
                self._stopped += 1
            if self._pending:
                self._push()
            else:
                self._close()

    def _push(self) -> None:
        if jobs is None:
            return
        finished = self._total - len(self._pending)
        try:
            jobs.report(
                SOURCE,
                self.key,
                self.title,
                progress=finished / self._total,
                detail=f"{finished} of {self._total}",
                label=LABEL,
                href=HREF,
                stop=self._stop,
            )
        except Exception:  # noqa: BLE001 - the tray must never hurt a painting
            pass

    def _close(self) -> None:
        if jobs is None:
            return
        made = self._total - self._stopped
        try:
            if self._stopped:
                jobs.cancel(SOURCE, self.key, f"{made} of {self._total} finished")
            else:
                jobs.finish(SOURCE, self.key, f"{made} finished")
        except Exception:  # noqa: BLE001
            pass


def waiting(n: int, start: Callable[[], object]) -> None:
    """A card for paintings held back while the dashboard is being edited: "N
    paintings waiting", with a Paint now button that starts them (Tesserae
    0.457 and later; an older tray shows the card without the button)."""
    if jobs is None or n <= 0:
        return
    title = f"{n} painting{'' if n == 1 else 's'} waiting"
    detail = "Held while the dashboard is edited; Paint now starts them, within the daily limit"
    try:
        jobs.report(SOURCE, "waiting", title, detail=detail, label=LABEL, href=HREF, action=("Paint now", start))
    except TypeError:
        try:
            jobs.report(SOURCE, "waiting", title, detail=detail, label=LABEL, href=HREF)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def waiting_over(started: int) -> None:
    """The held paintings were started (or there are none left to wait for)."""
    if jobs is None:
        return
    try:
        if started:
            jobs.finish(SOURCE, "waiting", f"{started} painting{'' if started == 1 else 's'} started")
        else:
            jobs.clear(SOURCE, "waiting")
    except Exception:  # noqa: BLE001
        pass

