"""Paths and configuration.

* resource_dir(): bundled read-only data (data/), inside the .exe or the project folder.
* user_dir(): %APPDATA%/AoE2CounterOverlay – config.json, logs, icon cache. Same place for
  the .exe and for running from source, so settings survive rebuilds.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, dataclass, field


import os
import shutil

APP_NAME = "AoE2CounterOverlay"
PROJECT_DIR = pathlib.Path(__file__).resolve().parent.parent


def resource_dir() -> pathlib.Path:
    """Folder that contains data/ (PyInstaller unpack folder, or the project folder)."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    return PROJECT_DIR


def user_dir() -> pathlib.Path:
    """Writable per-user folder for config, logs and caches."""
    base = os.environ.get("APPDATA") or str(pathlib.Path.home())
    d = pathlib.Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


app_dir = resource_dir  # backwards-compatible name

CONFIG_FILE = user_dir() / "config.json"


def _migrate_old_files() -> None:
    """One-time move of config/icon cache from the project folder (older versions kept them there)."""
    old_cfg = PROJECT_DIR / "config.json"
    if not CONFIG_FILE.exists() and old_cfg.exists() and not getattr(sys, "frozen", False):
        shutil.copy2(old_cfg, CONFIG_FILE)
    old_icons = PROJECT_DIR / "data" / "cache" / "civ_icons"
    new_icons = user_dir() / "cache" / "civ_icons"
    if old_icons.is_dir() and not new_icons.exists() and not getattr(sys, "frozen", False):
        shutil.copytree(old_icons, new_icons)


@dataclass
class Config:
    profile_id: int = 0             # aoe2companion profile; 0 = ask on start ("who are you?")
    hotkey_toggle: str = "F9"
    hotkey_mode: str = "shift+F9"   # not F10: that opens AoE2's game menu
    hotkey_lock: str = "ctrl+F9"
    hide_after_game_s: int = 10     # keep the overlay readable on the score screen for a moment
    locked: bool = False            # click-through mode
    opacity: float = 0.82          # background opacity (0..1); text stays fully opaque
    font_size: int = 11
    compact: bool = True
    geometry: list[int] = field(default_factory=lambda: [40, 120, 460, 360])  # x, y, width, height

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            _migrate_old_files()
        except OSError:
            pass
        if CONFIG_FILE.exists():
            try:
                # utf-8-sig: also accepts files with BOM (e.g. saved by Notepad/PowerShell)
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                # migration: the old default F10 is AoE2's game menu key
                if cfg.hotkey_mode.strip().lower() == "f10":
                    cfg.hotkey_mode = "shift+F9"
                if any(k not in data for k in asdict(cfg)) or data.get("hotkey_mode") != cfg.hotkey_mode:
                    cfg.save()
            except (json.JSONDecodeError, OSError) as e:
                print(f"config.json unreadable ({e}), using defaults")
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
