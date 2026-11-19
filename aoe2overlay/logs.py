"""Log files in the user folder: overlay.log (app events, errors) and socket-raw.log
(every live message as received, to check later what the server sent during a game)."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import user_dir

raw_log = logging.getLogger("aoe2overlay.raw")
raw_log.propagate = False


def setup_logging() -> None:
    d = user_dir()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    main = RotatingFileHandler(d / "overlay.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    main.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(main)
    if sys.stderr is not None:          # console when run from source; the .exe has none
        root.addHandler(logging.StreamHandler())

    raw = RotatingFileHandler(d / "socket-raw.log", maxBytes=2_000_000, backupCount=1, encoding="utf-8")
    raw.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    raw_log.addHandler(raw)
    raw_log.setLevel(logging.INFO)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("aoe2overlay").critical("Unhandled error", exc_info=(exc_type, exc, tb))
    sys.excepthook = excepthook
    threading.excepthook = lambda a: excepthook(a.exc_type, a.exc_value, a.exc_traceback)
