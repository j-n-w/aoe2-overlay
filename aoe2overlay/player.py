"""Choosing whose games the overlay follows.

On the first start (no profile_id in config.json) and from the tray menu the overlay asks
"Who are you?": a list of the Stammtisch players from age-stammtisch.de, or any aoe2companion
profile id / profile link typed into the same box.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request

from PySide6.QtWidgets import QInputDialog, QMessageBox

from .match import USER_AGENT

log = logging.getLogger(__name__)

STAMMTISCH_URL = "https://age-stammtisch.de/liga/api.php?action=get"
PROFILE_URL = "https://data.aoe2companion.com/api/profiles/{pid}"


def _get_json(url: str, timeout: float = 6):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def stammtisch_players() -> list[tuple[str, int]]:
    """(name, profile id) of the league players, sorted by name; empty if the site can't be reached."""
    try:
        data = _get_json(STAMMTISCH_URL)
        players = data["state"]["config"]["players"]
        out = [(str(p["name"]), int(p["id"])) for p in players if int(p.get("id", 0)) > 0]
        return sorted(out, key=lambda x: x[0].lower())
    except Exception as e:  # offline, site down, format change: typing an id still works
        log.warning("stammtisch players: %r", e)
        return []


def profile_name(pid: int) -> str | None:
    """Player name on aoe2companion, None if unknown or unreachable."""
    try:
        return _get_json(PROFILE_URL.format(pid=pid)).get("name") or None
    except Exception as e:
        log.warning("profile %s: %r", pid, e)
        return None


def parse_profile(text: str, known: dict[str, int]) -> int | None:
    """A list entry, a plain id, or an aoe2companion / aoe2insights profile link -> profile id."""
    t = text.strip()
    if t in known:
        return known[t]
    m = re.search(r"profile[s]?/(\d+)|user/(\d+)", t)
    if m:
        return int(m.group(1) or m.group(2))
    nums = re.findall(r"\d{3,}", t)
    return int(nums[-1]) if len(nums) == 1 else None


def ask_player(current: int = 0) -> tuple[int, str] | None:
    """Shows the "Who are you?" box until a valid profile is chosen: (profile id, name). None = cancelled."""
    players = stammtisch_players()
    known = {f"{name}  ({pid})": pid for name, pid in players}
    items = list(known)
    idx = next((i for i, pid in enumerate(known.values()) if pid == current), 0)
    hint = ("Pick your name, or type your aoe2companion profile id or profile link\n"
            "(aoe2companion.com → your profile → the number in the address).")
    text = ""
    while True:
        text, ok = QInputDialog.getItem(None, "AoE2 Counter Overlay – who are you?", hint,
                                        items or [text], idx if items else 0, True)
        if not ok:
            return None
        pid = parse_profile(text, known)
        if pid is None:
            QMessageBox.warning(None, "AoE2 Counter Overlay", "That is not a profile id or profile link.")
            continue
        if pid in known.values():
            return pid, next(n for n, p in players if p == pid)
        name = profile_name(pid)
        if name is None:
            again = QMessageBox.question(
                None, "AoE2 Counter Overlay",
                f"aoe2companion doesn't know profile {pid} (or can't be reached). Use it anyway?")
            if again != QMessageBox.Yes:
                continue
        return pid, name or ""


def player_label(pid: int, name: str) -> str:
    return name or f"profile {pid}"
