"""Team plan: combines the computed counters for all opponents (no hand-written advice).

* build      – your units that answer the most enemy key units (official "Weak vs." texts)
* picks      – your units whose specific counters none of the enemies has (counters.good_picks)
* no_answer  – enemy key units you have no listed counter for
* shared_gaps – tech-tree gaps that several enemies have in common (from the tech trees)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .civdata import Civ
from .counters import CivCounters, Pick, counters_for, good_picks
from .match import Player


@dataclass
class TeamPlan:
    per_enemy: list[tuple[Player, CivCounters]]
    build: list[tuple[str, list[str]]] = field(default_factory=list)   # (your unit, enemy units it answers)
    picks: list[Pick] = field(default_factory=list)
    no_answer: list[str] = field(default_factory=list)
    shared_gaps: list[tuple[str, int]] = field(default_factory=list)   # (gap, how many enemies)
    enemy_count: int = 0


def plan(opponents: list[Player], own: Civ | None) -> TeamPlan:
    per_enemy = [(p, counters_for(p.civ, own)) for p in opponents if p.civ]
    answered: dict[str, list[str]] = {}
    order: list[str] = []
    no_answer: list[str] = []
    for _, cc in per_enemy:
        for t in cc.threats:
            if not t.answers:
                no_answer.append(f"{t.name} ({cc.civ.name})")
            # only the first two answers count – they are the official main counters
            for a in t.answers[:2]:
                if a not in answered:
                    answered[a] = []
                    order.append(a)
                if t.name not in answered[a]:
                    answered[a].append(t.name)
    build = sorted(((a, answered[a]) for a in order), key=lambda x: (-len(x[1]), order.index(x[0])))
    enemies = [cc.civ for _, cc in per_enemy]
    return TeamPlan(
        shared_gaps=shared_gaps(enemies),
        enemy_count=len(enemies),
        per_enemy=per_enemy,
        build=build[:3],
        picks=good_picks(own, enemies) if own else [],
        no_answer=sorted(set(no_answer)),
    )


def shared_gaps(enemies: list[Civ], limit: int = 4) -> list[tuple[str, int]]:
    """Gaps that at least two enemy civs share (only meaningful with 2+ enemies).
    Duplicate civs count once per player, since each player is a separate army."""
    if len(enemies) < 2:
        return []
    count: dict[str, int] = {}
    order: list[str] = []
    for civ in enemies:
        for g in civ.gaps:
            if g not in count:
                count[g] = 0
                order.append(g)
            count[g] += 1
    shared = [(g, n) for g, n in count.items() if n >= 2]
    shared.sort(key=lambda x: (-x[1], order.index(x[0])))
    return shared[:limit]
