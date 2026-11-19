"""Map info: official description (game files) + sourced notes (data/maps.en.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import app_dir

DATA = app_dir() / "data"


@dataclass
class MapInfo:
    name: str
    official: str = ""
    resources: str = ""
    extra: str = ""
    tips: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def has_notes(self) -> bool:
        return bool(self.resources or self.tips)


def _norm(s: str) -> str:
    s = s.lower().removeprefix("rm_")
    return re.sub(r"[^a-z0-9]", "", s)


@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict]:
    def read(name):
        p = DATA / name
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}
    return read("maps.en.json"), read("maps_official.json")


def find_map(map_name: str, map_enum: str | None = None) -> MapInfo | None:
    notes, official = _load()
    keys = [k for k in (map_name, map_enum) if k]
    if not keys:
        return None
    wanted = [_norm(k) for k in keys]

    def match(name: str, aliases: list[str]) -> bool:
        cands = [_norm(name)] + [_norm(a) for a in aliases]
        # exact match first; custom maps often carry a version suffix ("Rage Forest v3")
        return any(w == c or (len(c) >= 6 and c in w) for w in wanted for c in cands)

    note_key = next((k for k, v in notes.items() if not k.startswith("_") and match(k, v.get("aliases", []))), None)
    off_key = next((k for k in official if match(k, [])), None)
    if not note_key and not off_key:
        return MapInfo(name=map_name or map_enum or "")
    n = notes.get(note_key, {}) if note_key else {}
    return MapInfo(
        name=note_key or off_key or map_name,
        official=official.get(off_key or note_key or "", ""),
        resources=n.get("resources", ""),
        extra=n.get("extra", ""),
        tips=n.get("tips", []),
        sources=n.get("sources", []),
    )
