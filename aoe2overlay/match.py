"""Match model: players, teams, opponents. Parser for the aoe2companion format."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .civdata import Civ, find_civ

USER_AGENT = "aoe2-counter-overlay/1.1 (+https://github.com/j-n-w/aoe2-overlay)"
API_MATCHES = ("https://data.aoe2companion.com/api/matches?profile_ids={pid}"
               "&use_enums=true&page=1&per_page=1")


@dataclass
class Player:
    name: str
    profile_id: int | None
    civ_enum: str | None      # e.g. "bulgarians"; None if hidden
    team: int | None
    is_ai: bool = False
    color_hex: str | None = None   # in-game player color, e.g. "#405BFF"
    rating: int | None = None
    civ_image_url: str | None = None

    @property
    def civ(self) -> Civ | None:
        return find_civ(self.civ_enum) if self.civ_enum else None

    @property
    def display_name(self) -> str:
        return "AI" if self.is_ai else self.name


@dataclass
class Match:
    match_id: int | None
    map_name: str
    players: list[Player]
    own_profile_id: int
    finished: bool = False
    hide_civs: bool = False
    map_enum: str | None = None   # e.g. "rm_black_forest"

    @property
    def own_team(self) -> int | None:
        for p in self.players:
            if p.profile_id == self.own_profile_id:
                return p.team
        return None

    @property
    def opponents(self) -> list[Player]:
        own = self.own_team
        return [p for p in self.players if p.profile_id != self.own_profile_id and (own is None or p.team != own)]

    @property
    def me(self) -> Player | None:
        return next((p for p in self.players if p.profile_id == self.own_profile_id), None)

    @property
    def allies(self) -> list[Player]:
        own = self.own_team
        return [p for p in self.players if p.profile_id != self.own_profile_id and own is not None and p.team == own]

    @property
    def title(self) -> str:
        sizes = {}
        for p in self.players:
            sizes[p.team] = sizes.get(p.team, 0) + 1
        own = sizes.pop(self.own_team, 0)
        others = "v".join(str(n) for n in sizes.values())
        return f"{own}v{others} {self.map_name}".strip()


def parse_match(m: dict, own_profile_id: int) -> Match:
    """Converts a match object from the aoe2companion API (use_enums=true)."""
    # REST API nests players in teams[]; the websocket sends a flat players[] list
    raw_players: list[tuple[dict, int | None]] = []
    for team in m.get("teams") or []:
        for p in team.get("players") or []:
            raw_players.append((p, team.get("teamId")))
    for p in m.get("players") or []:
        raw_players.append((p, None))

    players: list[Player] = []
    for p, team_id in raw_players:
        pid = p.get("profileId")
        status = (p.get("status") or "").lower()
        is_ai = status == "ai" or pid is None or (isinstance(pid, int) and pid <= 0)
        players.append(Player(
            name=p.get("name") or "?",
            profile_id=pid,
            civ_enum=p.get("civ") or None,
            team=p.get("team", team_id),
            is_ai=is_ai,
            color_hex=p.get("colorHex"),
            rating=p.get("rating") if not is_ai else None,
            civ_image_url=p.get("civImageUrl"),
        ))
    return Match(
        match_id=m.get("matchId"),
        map_name=m.get("mapName") or m.get("map") or "",
        players=players,
        own_profile_id=own_profile_id,
        finished=bool(m.get("finished")),
        hide_civs=bool(m.get("hideCivs")),
        map_enum=m.get("map"),
    )


def fetch_last_match(profile_id: int) -> Match | None:
    req = urllib.request.Request(API_MATCHES.format(pid=profile_id), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    matches = data.get("matches") or []
    return parse_match(matches[0], profile_id) if matches else None


def demo_match(own_profile_id: int) -> Match:
    """3v3 Rage Forest vs Bulgarians, Bengalis and Incas (Incas as AI)."""
    P = Player
    return Match(
        match_id=None,
        map_name="Rage Forest",
        own_profile_id=own_profile_id,
        players=[
            P("[Mosel] Sir Fboard", own_profile_id, "franks", 1, color_hex="#405BFF", rating=1320),
            P("Teammate A", 1001, "britons", 1, color_hex="#00FF00", rating=1180),
            P("Teammate B", 1002, "mongols", 1, color_hex="#FFFF00", rating=1405),
            P("Enemy One", 2001, "bulgarians", 2, color_hex="#FF0000", rating=1550),
            P("Enemy Two With A Long Name", 2002, "bengalis", 2, color_hex="#00FFFF", rating=1290),
            P("AI (Extreme)", None, "incas", 2, is_ai=True, color_hex="#FF57B3"),
        ],
    )
