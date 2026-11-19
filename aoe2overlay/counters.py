"""Counter engine – derived only from official game data.

Sources (both from the game files via aoe2techtree):
  * each unit's in-game help text: "Strong vs. …" / "Weak vs. …"
  * each unit's armor classes and each civ's tech tree

Nothing in here is free-form advice. The only hand-made parts are the tables
below that translate the game's fixed vocabulary ("Spearman-line", "Archery
Units", …) into concrete unit lines. Check them against the game texts if a
result looks wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .civdata import Civ, _clean, _raw, find_civ, load_civs
from .config import app_dir

# ---------------------------------------------------------------------------
# Unit lines a player can build as counters: key -> stages (unit id, name), low -> high
# ---------------------------------------------------------------------------
LINES: dict[str, list[tuple[int, str]]] = {
    "spear": [(93, "Spearman"), (358, "Pikeman"), (359, "Halberdier")],
    "camel": [(329, "Camel Rider"), (330, "Heavy Camel Rider"), (207, "Imperial Camel Rider")],
    "knight": [(38, "Knight"), (283, "Cavalier"), (569, "Paladin")],
    "scout": [(448, "Scout Cavalry"), (546, "Light Cavalry"), (441, "Hussar")],
    "archer": [(4, "Archer"), (24, "Crossbowman"), (492, "Arbalester")],
    "skirm": [(7, "Skirmisher"), (6, "Elite Skirmisher")],
    "cav_archer": [(39, "Cavalry Archer"), (474, "Heavy Cav Archer")],
    "militia": [(74, "Militia"), (75, "Man-at-Arms"), (77, "Long Swordsman"),
                (473, "Two-Handed Swordsman"), (567, "Champion")],
    "hand_cannon": [(5, "Hand Cannoneer")],
    "mangonel": [(280, "Mangonel"), (550, "Onager"), (588, "Siege Onager")],
    "scorpion": [(279, "Scorpion"), (542, "Heavy Scorpion")],
    "eagle": [(751, "Eagle Scout"), (753, "Eagle Warrior"), (752, "Elite Eagle Warrior")],
    "monk": [(125, "Monk")],
}

# Stage that counts as a "full" counter when judging good picks (generic final upgrade,
# not civ-unique ones like Imperial Camel Rider or the rare Siege Onager)
FULL_STAGE: dict[str, int] = {
    "spear": 359, "camel": 330, "skirm": 6, "archer": 492, "militia": 567, "mangonel": 550,
    "scorpion": 542, "scout": 441, "cav_archer": 474, "eagle": 752,
}
FULL_STAGE_MATTERS = set(FULL_STAGE)

# Regional replacements: if a civ lacks the line, this counts instead (e.g. Champi Warrior for Militia)
LINE_FALLBACK: dict[str, list[tuple[int, str]]] = {
    "militia": [(2552, "Champi Warrior"), (2554, "Elite Champi Warrior")],
}

# "Weak vs." phrase in the game text -> lines that are meant
WEAK_PHRASE_LINES: dict[str, list[str]] = {
    "spearman-line": ["spear"],
    "camel riders": ["camel"],
    "cavalry": ["knight", "scout"],
    "archery units": ["archer", "cav_archer"],
    "units at close range": ["knight", "scout"],
    "monks": ["monk"],
    "skirmishers": ["skirm"],
    "ranged soldiers": ["archer", "hand_cannon"],
    "ranged soldiers at long range": ["archer"],
    "foot archers": ["archer"],
    "foot archers at long range": ["archer"],
    "siege weapons": ["mangonel", "scorpion"],
    "gunners": ["hand_cannon"],
    "militia-line": ["militia"],
    "infantry": ["militia"],
    "mangonel-line": ["mangonel"],
    "scorpions": ["scorpion"],
    "melee units": ["militia", "knight"],
    "mounted archers": ["cav_archer"],
    "scout cavalry-line": ["scout"],
    "eagle warriors": ["eagle"],
}
# Broad phrases that almost every civ can answer – ignored when judging "good picks"
BROAD_PHRASES = {"units at close range", "monks", "cavalry", "melee units", "infantry",
                 "ranged soldiers", "ranged soldiers at long range", "archery units"}

# "Strong vs." phrase -> armor classes it refers to (to find own unique units that beat an enemy unit)
STRONG_PHRASE_CLASSES: dict[str, set[int]] = {
    "infantry": {1}, "cavalry": {8}, "mounted units": {8}, "ranged soldiers": {15},
    "archery units": {15}, "foot archers": {15}, "siege weapons": {20}, "mounted archers": {28},
    "spearman-line": {27}, "camel riders": {30}, "monastery units": {25}, "unique units": {19},
    "especially elephants": {5}, "especially elephants)": {5},
}

# Civ "kind" / bonus keywords -> line or unit that is a key threat (checked in this order)
THREAT_KEYWORDS: list[tuple[str, str]] = [
    ("cavalry archer", "cav_archer"), ("mounted archer", "cav_archer"),
    ("camel", "camel"), ("elephant", "elephant"), ("steppe lancer", "steppe_lancer"),
    ("eagle", "eagle"), ("hand cannon", "hand_cannon"), ("gunpowder", "hand_cannon"),
    ("knight", "knight"), ("cavalier", "knight"), ("paladin", "knight"),
    ("light cavalry", "scout"), ("hussar", "scout"), ("scout cavalry", "scout"),
    ("slinger", "slinger"), ("foot archer", "archer"), ("archer", "archer"), ("crossbow", "archer"),
    ("militia", "militia"), ("infantry", "militia"), ("swordsm", "militia"), ("champion", "militia"),
    ("champi", "militia"),
    ("siege weapon", "mangonel"), ("siege unit", "mangonel"), ("mangonel", "mangonel"),
    ("onager", "mangonel"), ("scorpion", "scorpion"),
    ("monk", "monk"), ("cavalry", "knight"), ("mounted", "knight"),
]
EXTRA_THREAT_LINES = {
    "elephant": [(1132, "Battle Elephant"), (1134, "Elite Battle Elephant")],
    "steppe_lancer": [(1370, "Steppe Lancer"), (1372, "Elite Steppe Lancer")],
    "slinger": [(185, "Slinger")],
}
MAX_THREATS = 4


@dataclass
class Threat:
    name: str                      # e.g. "Konnik" or "Heavy Cav Archer"
    unit_id: int
    unique: bool
    blurb: str                     # official one-liner, e.g. "Bulgarian unique Heavy Cavalry …"
    weak_vs: list[str]             # official phrases
    answers: list[str] = field(default_factory=list)   # what the viewer can build (stage names)


@dataclass
class CivCounters:
    civ: Civ
    threats: list[Threat]


# ---------------------------------------------------------------------------
# Game text helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _game_unit_texts() -> dict:
    """Fallback texts read from the local game files (tools/update_maps.py)."""
    import json
    p = app_dir() / "data" / "unit_texts_game.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


@lru_cache(maxsize=None)
def unit_name(uid: int) -> str:
    data, strings, _ = _raw()
    u = data["data"]["Unit"].get(str(uid), {})
    name = strings.get(str(u.get("LanguageNameId", 0) + 9000))
    if not name:
        name = _game_unit_texts().get(str(uid), {}).get("name") or u.get("internal_name", str(uid))
    return _clean(name)


@lru_cache(maxsize=None)
def unit_help(uid: int) -> str:
    data, strings, _ = _raw()
    u = data["data"]["Unit"].get(str(uid), {})
    text = strings.get(str(u.get("LanguageNameId", 0) + 21000)) or _game_unit_texts().get(str(uid), {}).get("help", "")
    text = re.sub(r"<(cost|GREY|DEFAULT|hp|attack|armor|piercearmor|range)>", "", text)
    return _clean(text).split("Upgrades:")[0]


def _phrases(text: str, kind: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(kind + r" vs\.?\s*([^.]*)\.", text, re.I):
        for part in re.split(r",\s*|\s+and\s+|\s+or\s+", m.group(1)):
            part = part.strip().removeprefix("and ").strip()
            if part:
                out.append(part)
    return out


def weak_vs(uid: int) -> list[str]:
    return _phrases(unit_help(uid), "Weak")


def strong_vs(uid: int) -> list[str]:
    return _phrases(unit_help(uid), "(?:Exceptionally strong|Strong)")


def blurb(uid: int) -> str:
    """First sentence(s) of the help text after 'Create <name> (cost)'."""
    text = re.sub(r"^(Create|Build)\s+.*?\((‹cost›)?\)\s*", "", unit_help(uid)).strip()
    return text.split(" Strong vs")[0].split(" Weak vs")[0].split(" Exceptionally")[0].strip()


def armor_classes(uid: int) -> set[int]:
    data, _, _ = _raw()
    return {a["Class"] for a in data["data"]["Unit"].get(str(uid), {}).get("Armours", [])}


def top_stage(civ: Civ, line: str) -> tuple[int, str] | None:
    stages = LINES.get(line) or EXTRA_THREAT_LINES.get(line) or []
    have = [(uid, nm) for uid, nm in stages if uid in civ.units]
    if not have:
        have = [(uid, nm) for uid, nm in LINE_FALLBACK.get(line, []) if uid in civ.units]
    return have[-1] if have else None


def has_full_stage(civ: Civ, line: str) -> bool:
    return FULL_STAGE[line] in civ.units


# ---------------------------------------------------------------------------
# Unique units
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _unit_holders() -> dict[int, int]:
    holders: dict[int, int] = {}
    for c in load_civs().values():
        for u in c.units:
            holders[u] = holders.get(u, 0) + 1
    return holders


def unique_unit_ids(civ: Civ) -> list[int]:
    """Unique land units of a civ, matched by the names in its official help text."""
    wanted = [u.split("(")[0].strip().lower() for u in civ.unique_units
              if "(Hero)" not in u and "Warship" not in u and "ship" not in u.lower().split("(")[-1]]
    ids: list[int] = []
    for name in wanted:
        matches = [uid for uid in civ.units if unit_name(uid).lower() == name]
        if matches:
            ids.append(min(matches))   # base version (elite has the higher id)
    return ids


# ---------------------------------------------------------------------------
# Threats of an enemy civ and answers for the viewer's civ
# ---------------------------------------------------------------------------
def threats_of(civ: Civ) -> list[Threat]:
    """Order: first unique unit, first unit type named in the civ's official type line,
    remaining unique units, then units named in bonuses/unique techs."""
    seen_lines: set[str] = set()

    def from_text(text: str, limit: int) -> list[Threat]:
        found: list[Threat] = []
        for kw, line in THREAT_KEYWORDS:
            if len(found) >= limit:
                break
            if line in seen_lines or kw not in text:
                continue
            stage = top_stage(civ, line)
            if not stage:
                continue
            seen_lines.add(line)
            uid, name = stage
            found.append(Threat(name, uid, False, blurb(uid), weak_vs(uid)))
        return found

    uniques = [Threat(unit_name(u), u, True, blurb(u), weak_vs(u)) for u in unique_unit_ids(civ)]
    kind = from_text(civ.kind.lower(), 2)
    ordered = uniques[:1] + kind[:1] + uniques[1:] + kind[1:]
    ordered += from_text(" ".join(civ.bonuses + civ.unique_techs).lower(), MAX_THREATS)
    out: list[Threat] = []
    for t in ordered:
        if not any(o.unit_id == t.unit_id for o in out):
            out.append(t)
    return out[:MAX_THREATS]


def answers_for(threat: Threat, own: Civ | None) -> list[str]:
    """Units the viewer can build against a threat, best stage, official counters first."""
    result: list[str] = []
    for phrase in threat.weak_vs:
        for line in WEAK_PHRASE_LINES.get(phrase.lower(), []):
            if own is None:
                name = LINES[line][-1][1]
            else:
                stage = top_stage(own, line)
                if not stage:
                    continue
                name = stage[1]
            if name not in result:
                result.append(name)
    # own unique units whose official "Strong vs." matches the threat's armor classes
    if own is not None:
        classes = armor_classes(threat.unit_id)
        for uid in unique_unit_ids(own):
            hits = [p for p in strong_vs(uid) if STRONG_PHRASE_CLASSES.get(p.lower(), set()) & classes]
            name = unit_name(uid)
            if hits and name not in result:
                result.append(name)
    return result


def counters_for(enemy: Civ, own: Civ | None) -> CivCounters:
    threats = threats_of(enemy)
    for t in threats:
        t.answers = answers_for(t, own)
    return CivCounters(enemy, threats)


# ---------------------------------------------------------------------------
# Good picks: own units whose specific counters the enemies lack
# ---------------------------------------------------------------------------
@dataclass
class Pick:
    unit: str
    reason: str


def good_picks(own: Civ, enemies: list[Civ]) -> list[Pick]:
    if not enemies:
        return []
    candidates: list[tuple[int, str]] = [(uid, unit_name(uid)) for uid in unique_unit_ids(own)]
    for line in ("knight", "archer", "cav_archer", "militia", "scout", "camel", "hand_cannon", "eagle"):
        stage = top_stage(own, line)
        if stage:
            candidates.append(stage)
    candidates += [s for s in (top_stage(own, "elephant"), top_stage(own, "steppe_lancer")) if s]

    picks: list[Pick] = []
    for uid, name in candidates:
        specific = [p for p in weak_vs(uid) if p.lower() not in BROAD_PHRASES and p.lower() in WEAK_PHRASE_LINES]
        if not specific:
            continue
        lines = {l for p in specific for l in WEAK_PHRASE_LINES[p.lower()]}
        lines &= FULL_STAGE_MATTERS
        if not lines:
            continue
        # an enemy "answers" the unit if it has the full stage of any specific counter line
        answering = [e for e in enemies if any(has_full_stage(e, l) for l in lines)]
        if not answering:
            missing = sorted({LINES[l][-1][1] for l in lines})
            picks.append(Pick(name, f"no enemy has {' / '.join(missing)}"))
    return picks[:3]


if __name__ == "__main__":
    import sys
    own = find_civ(sys.argv[1]) if len(sys.argv) > 1 else find_civ("franks")
    enemies = [find_civ(n) for n in (sys.argv[2:] or ["tatars", "bulgarians", "incas"])]
    print(f"You: {own.name}")
    for e in enemies:
        cc = counters_for(e, own)
        print(f"== {e.name}")
        for t in cc.threats:
            print(f"  {'*' if t.unique else ' '} {t.name}: weak vs {t.weak_vs} -> you: {t.answers or 'NONE'}")
    for p in good_picks(own, enemies):
        print("  good pick:", p.unit, "–", p.reason)
