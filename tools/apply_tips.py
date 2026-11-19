"""Merges researched civ tips (JSON file: {civ_key: entry}) into data/civ_tips.en.json.

Each entry replaces the existing one completely. Adds "checked" (date) if missing.

Usage:
    .venv\\Scripts\\python.exe tools\\apply_tips.py path\\to\\batch.json
"""

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIPS = ROOT / "data" / "civ_tips.en.json"

batch = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
tips = json.loads(TIPS.read_text(encoding="utf-8-sig"))
today = dt.date.today().isoformat()
for key, entry in batch.items():
    if key not in tips:
        print(f"WARNING: {key} is not in civ_tips.en.json – added anyway")
    entry.setdefault("checked", today)
    tips[key] = entry
TIPS.write_text(json.dumps(tips, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"updated {len(batch)} civs: {', '.join(batch)}")
