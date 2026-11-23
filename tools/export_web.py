"""Exports the overlay's computed counter data for the website edition (age-stammtisch.de, Live tab).

The website does not re-implement the counter engine: everything that depends on the game data is
computed here with the same code as the overlay and written as compact JSON:

  civs[key]   name, type line, gaps, team bonus, unique units, sourced notes (civ_tips.en.json),
              threats (= threats_of), full-stage lines (for good picks), good-pick candidates
  ans[own][threat unit id]  answers_for(threat, own) as indexes into names[]
  alias       aoe2companion civ enum / display name -> key

The browser then only combines these per game (team plan = analysis.plan without game data).
Usage: python tools/export_web.py <output.json>
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from aoe2overlay.civdata import load_civs  # noqa: E402
from aoe2overlay import counters as K  # noqa: E402


def main(out: str) -> None:
    civs = load_civs()
    names: list[str] = []
    idx: dict[str, int] = {}

    def nid(n: str) -> int:
        if n not in idx:
            idx[n] = len(names)
            names.append(n)
        return idx[n]

    data: dict = {'civs': {}, 'ans': {}, 'alias': {}}
    threat_ids: dict[int, K.Threat] = {}
    for key, c in sorted(civs.items()):
        ths = K.threats_of(c)
        for t in ths:
            threat_ids[t.unit_id] = t
        # good-pick candidates of this civ as "own" civ (same as counters.good_picks before the enemy check)
        cand = [(uid, K.unit_name(uid)) for uid in K.unique_unit_ids(c)]
        for line in ("knight", "archer", "cav_archer", "militia", "scout", "camel", "hand_cannon", "eagle"):
            st = K.top_stage(c, line)
            if st:
                cand.append(st)
        cand += [s for s in (K.top_stage(c, "elephant"), K.top_stage(c, "steppe_lancer")) if s]
        pcs = []
        for uid, name in cand:
            specific = [p for p in K.weak_vs(uid) if p.lower() not in K.BROAD_PHRASES and p.lower() in K.WEAK_PHRASE_LINES]
            if not specific:
                continue
            lines = {l for p in specific for l in K.WEAK_PHRASE_LINES[p.lower()]} & K.FULL_STAGE_MATTERS
            if lines:
                pcs.append([name, sorted(lines), ' / '.join(sorted({K.LINES[l][-1][1] for l in lines}))])
        tips = c.tips or {}
        data['civs'][key] = {
            'n': c.name, 'kind': c.kind, 'gaps': c.gaps, 'tb': c.team_bonus,
            'uu': [u.split('(')[0].strip() for u in c.unique_units],
            'prof': tips.get('profile', ''), 'dang': tips.get('dangers', []),
            'th': [[t.unit_id, t.name, 1 if t.unique else 0, t.weak_vs] for t in ths],
            'full': sorted(l for l in K.FULL_STAGE if K.has_full_stage(c, l)),
            'pc': pcs,
        }
        for a in {key, c.name, re.sub(r'[^a-z]', '', c.name.lower()), re.sub(r'[^a-z]', '', key.lower())}:
            data['alias'][re.sub(r'[^a-z]', '', a.lower())] = key
    data['alias'].setdefault('indians', 'Hindustanis')  # name before the 2023 split, still in older games
    for own_key, own in sorted(civs.items()):
        row = {}
        for uid, t in threat_ids.items():
            row[str(uid)] = [nid(a) for a in K.answers_for(t, own)]
        data['ans'][own_key] = row
    data['names'] = names
    pathlib.Path(out).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(civs)} civs, {len(threat_ids)} threat units, {len(names)} names -> {out} ({pathlib.Path(out).stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'overlay-data.json')
