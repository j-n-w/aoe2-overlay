"""Prints a short overview of all civs (sanity check after a data update)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aoe2overlay.civdata import load_civs  # noqa: E402

full = "--full" in sys.argv
for c in load_civs().values():
    techs = "; ".join(t.split("(")[0].strip() for t in c.unique_techs)
    print(f"{c.key} | {c.kind} | UU: {'; '.join(c.unique_units)} | UT: {techs}"
          f" | caps: {','.join(sorted(c.capabilities))} | tips: {'yes' if c.tips else 'MISSING'}")
    if full:
        print("   gaps:", " | ".join(c.gaps))
        print("   minor:", " | ".join(c.minor_gaps))
        print("   bonuses:", " | ".join(c.bonuses))
        print("   team:", c.team_bonus)
