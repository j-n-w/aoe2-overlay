"""Civ icons from the aoe2companion CDN, downloaded once and cached in the user folder (cache/civ_icons)."""

from __future__ import annotations

import threading
import urllib.request

from PySide6.QtCore import QObject, QUrl, Signal

from .config import user_dir
from .match import USER_AGENT

CDN = "https://backend.cdn.aoe2companion.com/public/aoe2/de/civilizations/{civ}.png"
CACHE = user_dir() / "cache" / "civ_icons"


class IconCache(QObject):
    ready = Signal()   # emitted (from a worker thread) after new icons were downloaded

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._lock = threading.Lock()

    def get(self, civ: str, url: str | None = None) -> str | None:
        """Local file URL of the icon, or None (download starts in the background)."""
        path = CACHE / f"{civ}.png"
        if path.exists():
            return QUrl.fromLocalFile(str(path)).toString()
        with self._lock:
            if civ in self._pending or civ in self._failed:
                return None
            self._pending.add(civ)
        threading.Thread(target=self._download, args=(civ, url or CDN.format(civ=civ)), daemon=True).start()
        return None

    def _download(self, civ: str, url: str) -> None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            if not data.startswith(b"\x89PNG"):
                raise ValueError("not a PNG")
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = CACHE / f"{civ}.png.part"
            tmp.write_bytes(data)
            tmp.replace(CACHE / f"{civ}.png")
            ok = True
        except Exception:
            ok = False
        with self._lock:
            self._pending.discard(civ)
            if not ok:
                self._failed.add(civ)   # don't retry in this session
            done = not self._pending
        if ok and done:
            self.ready.emit()
