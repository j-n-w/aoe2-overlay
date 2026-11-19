"""Optional autostart for the .exe: a value in HKCU\\...\\Run (current user only, no admin).
Toggled from the tray menu; nothing is written unless the user ticks "Start with Windows"."""

from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "AoE2CounterOverlay"


def available() -> bool:
    """Only for the packaged .exe – a source checkout has no stable command to start."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _command() -> str:
    return f'"{sys.executable}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            value, _ = winreg.QueryValueEx(k, VALUE)
        return bool(value)
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if not available():
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except FileNotFoundError:
                pass
