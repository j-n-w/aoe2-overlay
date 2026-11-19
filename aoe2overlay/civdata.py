"""Data layer: load civilizations from aoe2techtree and derive tech-tree gaps.

Sources: data/techtree/ (refresh with tools/update_techtree.py) and
data/civ_tips.en.json (hand-written strategy notes).
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import app_dir

ROOT = app_dir()
TECHTREE_DIR = ROOT / "data" / "techtree"
TIPS_FILE = ROOT / "data" / "civ_tips.en.json"
STRINGS_FILE = "strings_en.json"

# ---------------------------------------------------------------------------
# What gets checked
# ---------------------------------------------------------------------------
# Unit lines: (line name, [(unit id, stage name), ...] from lowest to highest)
UNIT_LINES: list[tuple[str, list[tuple[int, str]]]] = [
    ("Knight", [(38, "Knight"), (283, "Cavalier"), (569, "Paladin")]),
    ("Scout", [(448, "Scout Cavalry"), (546, "Light Cavalry"), (441, "Hussar")]),
    ("Camel", [(329, "Camel Rider"), (330, "Heavy Camel Rider")]),
    ("Cav Archer", [(39, "Cavalry Archer"), (474, "Heavy Cav Archer")]),
    ("Archer", [(4, "Archer"), (24, "Crossbowman"), (492, "Arbalester")]),
    ("Skirmisher", [(7, "Skirmisher"), (6, "Elite Skirmisher")]),
    ("Militia", [(74, "Militia"), (75, "Man-at-Arms"), (77, "Long Swordsman"),
                 (473, "Two-Handed Swordsman"), (567, "Champion")]),
    ("Spear", [(93, "Spearman"), (358, "Pikeman"), (359, "Halberdier")]),
    ("Ram", [(1258, "Battering Ram"), (422, "Capped Ram"), (548, "Siege Ram")]),
    ("Mangonel", [(280, "Mangonel"), (550, "Onager"), (588, "Siege Onager")]),
    ("Scorpion", [(279, "Scorpion"), (542, "Heavy Scorpion")]),
    ("Trebuchet", [(331, "Trebuchet")]),
    ("Gunpowder", [(5, "Hand Cannoneer"), (36, "Bombard Cannon")]),
    ("Fire Ship", [(529, "Fire Galley"), (1103, "Fire Ship"), (532, "Fast Fire Ship")]),
    ("Cannon Galleon", [(420, "Cannon Galleon"), (691, "Elite Cannon Galleon")]),
]

# Civ-specific replacements: if the line is missing but this unit exists, it is no gap
LINE_REPLACEMENTS: dict[str, list[int]] = {
    "Ram": [1744],          # Armored Elephant
    "Trebuchet": [1942],    # Traction Trebuchet
    "Militia": [2552],      # Champi Warrior
}

LINE_PLURAL = {
    "Knight": "Knights", "Scout": "Scouts", "Camel": "Camels", "Cav Archer": "Cav Archers",
    "Archer": "Archers", "Skirmisher": "Skirmishers", "Militia": "Swordsmen", "Spear": "Spearmen",
    "Ram": "Rams", "Mangonel": "Mangonels", "Scorpion": "Scorpions", "Trebuchet": "Trebuchets",
    "Fire Ship": "Fire Ships", "Cannon Galleon": "Cannon Galleons",
}

# Single technologies: (tech id, display name, area)
TECHS: list[tuple[int, str, str]] = [
    (67, "Forging", "Melee attack"), (68, "Iron Casting", "Melee attack"),
    (75, "Blast Furnace", "Melee attack"),
    (74, "Scale Mail", "Infantry armor"), (76, "Chain Mail", "Infantry armor"),
    (77, "Plate Mail", "Infantry armor"),
    (81, "Scale Barding", "Cavalry armor"), (82, "Chain Barding", "Cavalry armor"),
    (80, "Plate Barding", "Cavalry armor"),
    (199, "Fletching", "Ranged attack"), (200, "Bodkin Arrow", "Ranged attack"),
    (201, "Bracer", "Ranged attack"),
    (211, "Padded Archer Armor", "Archer armor"), (212, "Leather Archer Armor", "Archer armor"),
    (219, "Ring Archer Armor", "Archer armor"),
    (435, "Bloodlines", "Stable"), (39, "Husbandry", "Stable"),
    (437, "Thumb Ring", "Archery range"), (436, "Parthian Tactics", "Archery range"),
    (215, "Squires", "Barracks"), (602, "Arson", "Barracks"), (875, "Gambesons", "Barracks"),
    (377, "Siege Engineers", "University"), (380, "Heated Shot", "University"),
    (379, "Hoardings", "University"), (321, "Sappers", "University"),
    (608, "Arrowslits", "University"), (51, "Architecture", "University"),
    (63, "Keep", "Towers"), (194, "Fortified Wall", "Walls"),
    (316, "Redemption", "Monastery"), (319, "Atonement", "Monastery"), (439, "Heresy", "Monastery"),
    (231, "Sanctity", "Monastery"), (233, "Illumination", "Monastery"),
    (438, "Theocracy", "Monastery"), (252, "Fervor", "Monastery"), (45, "Faith", "Monastery"),
    (230, "Block Printing", "Monastery"),
    (375, "Dry Dock", "Dock"), (373, "Shipwright", "Dock"),
    (14, "Horse Collar", "Economy"), (13, "Heavy Plow", "Economy"),
    (12, "Crop Rotation", "Economy"), (221, "Two-Man Saw", "Economy"),
    (182, "Gold Shaft Mining", "Economy"), (279, "Stone Shaft Mining", "Economy"),
    (15, "Guilds", "Economy"),
]

# Areas that matter during a fight (economy/monastery/dock are "minor" gaps)
MINOR_AREAS = {"Economy", "Monastery", "Dock", "Walls", "Towers", "University"}
WATER_LINES = {"Fire Ship", "Cannon Galleon"}  # mostly land maps are played

# Missing something counts as a real gap only if at least this share of all civs has it
GAP_SHARE = 0.5

# Capabilities for team analysis (unit ids, at least one present)
CAPABILITY_UNITS = {
    "camels": [329],
    "elephants": [1132, 1744, 873, 1120],
    "gunpowder": [5, 36],
    "cav_archers": [39],
    "paladin": [569],
    "siege_ram": [548],
    "siege_onager": [588],
    "halberdier": [359],
    "arbalester": [492],
    "elite_skirmisher": [6],
    "hussar": [441],
    "champion": [567],
}

# aoe2companion enum (lowercase) -> techtree key, only where they differ
COMPANION_ALIASES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Civ:
    key: str                      # techtree key, e.g. "Bulgarians"
    name: str                     # display name
    kind: str                     # e.g. "Infantry and Cavalry civilization"
    bonuses: list[str]
    unique_units: list[str]
    unique_techs: list[str]
    team_bonus: str
    gaps: list[str]               # derived: important tech-tree gaps
    minor_gaps: list[str]         # derived: economy/monastery/... gaps
    top_stages: dict[str, str]    # line -> highest stage ("—" = missing)
    capabilities: set[str]
    units: set[int] = field(default_factory=set)   # all unit ids from the tech tree
    techs: set[int] = field(default_factory=set)
    tips: dict = field(default_factory=dict)  # content of civ_tips.en.json


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = re.sub(r"-\s*<br>\s*", "-", text)
    text = text.replace("<br>", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", _TAG.sub("", text)).strip()


def _parse_help(text: str) -> dict:
    """Splits a civ's help text into sections."""
    lines = [l.strip().removesuffix("<br>").strip() for l in text.replace("\r", "").split("\n")]
    out = {"kind": "", "bonuses": [], "units": [], "techs": [], "team": ""}
    section = "bonuses"
    for i, line in enumerate(lines):
        if not line:
            continue
        if i == 0:
            out["kind"] = _clean(line)
            continue
        low = _clean(line).lower()
        rest = _clean(line.split("</b>", 1)[-1]) if "</b>" in line else ""
        if low.startswith("unique unit"):
            section = "units"
            if rest:
                out["units"].extend(_split_units(rest))
            continue
        if low.startswith("unique tech"):
            section = "techs"
            continue
        if low.startswith("team bonus"):
            section = "team"
            if rest:
                out["team"] = rest
            continue
        item = _clean(line).lstrip("•·").strip()
        if section == "bonuses":
            out["bonuses"].append(item)
        elif section == "units":
            out["units"].extend(_split_units(item))
        elif section == "techs":
            out["techs"].append(item)
        elif section == "team":
            out["team"] = (out["team"] + " " + item).strip()
    return out


def _split_units(item: str) -> list[str]:
    # several units separated by commas, ignoring commas inside parentheses
    return [p.strip() for p in re.split(r",\s*(?![^()]*\))", item) if p.strip()]


def _unit_name(data, strings, uid: int) -> str:
    u = data["data"]["Unit"].get(str(uid), {})
    # unit names live under LanguageNameId + 9000 in the strings file
    name = strings.get(str(u.get("LanguageNameId", 0) + 9000))
    return _clean(name) if name else u.get("internal_name", str(uid))


@lru_cache(maxsize=1)
def _raw():
    data = _load_json(TECHTREE_DIR / "data.json")
    strings = _load_json(TECHTREE_DIR / STRINGS_FILE)
    tips = _load_json(TIPS_FILE) if TIPS_FILE.exists() else {}
    return data, strings, tips


@lru_cache(maxsize=1)
def load_civs() -> dict[str, Civ]:
    data, strings, tips = _raw()
    civs_raw = data["civs"]
    n = len(civs_raw)

    unit_share: dict[int, float] = {}
    tech_share: dict[int, float] = {}
    for c in civs_raw.values():
        for u in c["Unit"]:
            unit_share[u] = unit_share.get(u, 0) + 1 / n
        for t in c["Tech"]:
            tech_share[t] = tech_share.get(t, 0) + 1 / n

    result: dict[str, Civ] = {}
    for key, c in civs_raw.items():
        units, techs = set(c["Unit"]), set(c["Tech"])
        help_ = _parse_help(strings.get(str(c["help_string_id"]), ""))

        gaps: list[str] = []
        minor: list[str] = []
        top: dict[str, str] = {}
        for line_name, stages in UNIT_LINES:
            have = [label for uid, label in stages if uid in units]
            alt = [uid for uid in LINE_REPLACEMENTS.get(line_name, []) if uid in units]
            if have:
                top[line_name] = have[-1]
            elif alt:
                top[line_name] = "replaced by " + _unit_name(data, strings, alt[0])
            else:
                top[line_name] = "—"
            target = minor if line_name in WATER_LINES else gaps
            if stages[0][0] not in units:
                if unit_share.get(stages[0][0], 0) >= GAP_SHARE and not alt:
                    target.append(f"no {LINE_PLURAL.get(line_name, line_name)}")
                continue
            # first missing stage that most civs have
            for i, (uid, _label) in enumerate(stages):
                if uid not in units:
                    if unit_share.get(uid, 0) >= GAP_SHARE:
                        target.append(f"no {stages[i][1]}")
                    break

        by_area: dict[str, list[str]] = {}
        for tid, label, area in TECHS:
            if tid not in techs and tech_share.get(tid, 0) >= GAP_SHARE:
                by_area.setdefault(area, []).append(label)
        for area, labels in by_area.items():
            (minor if area in MINOR_AREAS else gaps).append(f"{area}: no {', '.join(labels)}")

        result[key] = Civ(
            key=key,
            name=_clean(strings.get(str(c["name_string_id"]), key)),
            kind=help_["kind"],
            bonuses=help_["bonuses"],
            unique_units=help_["units"],
            unique_techs=help_["techs"],
            team_bonus=help_["team"],
            gaps=gaps,
            minor_gaps=minor,
            top_stages=top,
            capabilities={cap for cap, ids in CAPABILITY_UNITS.items() if units & set(ids)},
            units=units,
            techs=techs,
            tips=tips.get(key, {}),
        )
    return result


def find_civ(name: str) -> Civ | None:
    """Looks up a civ by aoe2companion enum ("bulgarians"), techtree key or display name."""
    civs = load_civs()
    low = name.strip().lower()
    low = COMPANION_ALIASES.get(low, low)
    for civ in civs.values():
        if low in (civ.key.lower(), civ.name.lower()):
            return civ
    return None


if __name__ == "__main__":
    import sys
    for nm in sys.argv[1:] or ["bulgarians", "bengalis", "incas"]:
        civ = find_civ(nm)
        if not civ:
            print(f"?? {nm}")
            continue
        print(f"== {civ.name} – {civ.kind}")
        print("  Unique units:", "; ".join(civ.unique_units))
        print("  Unique techs:", "; ".join(civ.unique_techs))
        print("  Team bonus:", civ.team_bonus)
        print("  Bonuses:", " | ".join(civ.bonuses))
        print("  Gaps:", " | ".join(civ.gaps) or "–")
        print("  Minor gaps:", " | ".join(civ.minor_gaps) or "–")
        print("  Top stages:", ", ".join(f"{k}: {v}" for k, v in civ.top_stages.items()))
        print("  Capabilities:", ", ".join(sorted(civ.capabilities)))
        print("  Tips:", "yes" if civ.tips else "missing")
