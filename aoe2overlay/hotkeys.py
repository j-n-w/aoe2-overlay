"""Global hotkeys via the Windows RegisterHotKey API.

Bindings are strings like "F9", "shift+F9", "ctrl+alt+o", "pause". Windows only reports
the registered combinations to us – there is no keyboard hook that sees every key press,
so typing in the game is never slowed down. A registered combination is consumed by
Windows and does not reach the game (F9 would otherwise open AoE2's hotkey overview).

The message loop runs in its own thread; callbacks are called from that thread, so the
receiver must switch to the GUI thread itself (Qt signal with QueuedConnection).
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Callable

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "alt": MOD_ALT, "win": MOD_WIN}
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_NAMED_KEYS = {
    "pause": 0x13, "scroll_lock": 0x91, "scrolllock": 0x91, "insert": 0x2D, "ins": 0x2D,
    "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23, "page_up": 0x21, "pageup": 0x21,
    "page_down": 0x22, "pagedown": 0x22, "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "enter": 0x0D, "return": 0x0D, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "print_screen": 0x2C, "num_lock": 0x90,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},                 # F1 = 0x70 … F24 = 0x87
    **{f"num{i}": 0x60 + i for i in range(10)},                   # numpad 0–9
}


def parse_key(name: str) -> int:
    """'F9' -> 0x78, 'pause' -> 0x13, 'o' -> ord('O'). Raises ValueError for unknown keys."""
    n = name.strip().lower()
    if n in _NAMED_KEYS:
        return _NAMED_KEYS[n]
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    raise ValueError(f"Unknown key: {name!r}")


def parse_binding(spec: str) -> tuple[int, int]:
    """'shift+F9' -> (MOD_SHIFT, VK_F9)."""
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey")
    mods = 0
    for p in parts[:-1]:
        if p.lower() not in MODIFIERS:
            raise ValueError(f"Unknown modifier {p!r} in {spec!r}")
        mods |= MODIFIERS[p.lower()]
    return mods, parse_key(parts[-1])


class HotkeyListener:
    """start() registers all bindings; `errors` lists the ones Windows refused (key in use)."""

    def __init__(self, bindings: dict[str, Callable[[], None]]):
        self._bindings = [(spec, parse_binding(spec), cb) for spec, cb in bindings.items()]  # may raise
        self.errors: list[str] = []
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if sys.platform != "win32":
            self.errors = ["global hotkeys are only supported on Windows"]
            return
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)   # so `errors` is filled when start() returns

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(1.0)

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        callbacks: dict[int, Callable[[], None]] = {}
        for hk_id, (spec, (mods, vk), cb) in enumerate(self._bindings, start=1):
            if user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
                callbacks[hk_id] = cb
            else:
                self.errors.append(f"{spec} is already used by another program")
                log.warning("RegisterHotKey failed for %s", spec)
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in callbacks:
                    try:
                        callbacks[msg.wParam]()
                    except Exception:
                        log.exception("hotkey callback failed")
        finally:
            for hk_id in callbacks:
                user32.UnregisterHotKey(None, hk_id)
