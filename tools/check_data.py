"""Checks the data layer. Run after every data update (tools/update_techtree.py, update_maps.py).

Guards against unsourced or unmapped content:
  * every civ has sourced notes (profile, dangers, sources)
  * the counter engine finds key units for every civ, every unique land unit is matched,
    and every "Weak vs." phrase in the game texts is mapped to unit lines
  * every map note has a source
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aoe2overlay import counters as C  # noqa: E402
from aoe2overlay.civdata import find_civ, load_civs  # noqa: E402

problems: list[str] = []
warnings: list[str] = []
civs = load_civs()

for c in civs.values():
    # sourced notes
    for f in ("profile", "dangers", "sources"):
        if not c.tips.get(f):
            problems.append(f"{c.key}: civ_tips field '{f}' missing")
    extra = set(c.tips) - {"profile", "dangers", "sources", "checked"}
    if extra:
        problems.append(f"{c.key}: unexpected civ_tips fields {sorted(extra)} – counters must not be hand-written")

    # counter engine
    land_uu = [u for u in c.unique_units if "(Hero)" not in u and "ship" not in u.lower()]
    found = C.unique_unit_ids(c)
    if len(found) < len(land_uu):
        names = [C.unit_name(i) for i in found]
        warnings.append(f"{c.key}: unique units {land_uu} – matched only {names}")
    threats = C.threats_of(c)
    if not threats:
        problems.append(f"{c.key}: no key units found")
    for t in threats:
        if not t.weak_vs:
            warnings.append(f"{c.key}: {t.name} has no 'Weak vs.' text")
        for ph in t.weak_vs:
            if ph.lower() not in C.WEAK_PHRASE_LINES and ph.lower() != "other units":
                problems.append(f"{c.key}: phrase '{ph}' ({t.name}) not mapped in counters.WEAK_PHRASE_LINES")

# aoe2companion sends lowercase enums
for enum in ["malay", "italians", "spanish", "celts", "bulgarians", "bengalis", "incas", "sicilians", "franks"]:
    if not find_civ(enum):
        problems.append(f"enum '{enum}' cannot be mapped")

# maps
maps = json.loads((ROOT / "data" / "maps.en.json").read_text(encoding="utf-8-sig"))
for k, v in maps.items():
    if k.startswith("_"):
        continue
    if not v.get("sources"):
        problems.append(f"map {k}: no sources")
if not (ROOT / "data" / "maps_official.json").exists():
    warnings.append("data/maps_official.json missing – run tools/update_maps.py")

print(f"{len(civs)} civs, {len(maps) - 1} map notes checked.")
for w in warnings:
    print("warning:", w)
print("\n".join(problems) if problems else "No problems.")
sys.exit(1 if problems else 0)
