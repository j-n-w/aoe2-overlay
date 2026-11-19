"""Downloads the current tech-tree data from SiegeEngineers/aoe2techtree.

Fetches data/data.json and the English strings into data/techtree/ and then
lists the included civs, so you can check that new DLC civs are present.

Usage:
    .venv\\Scripts\\python.exe tools\\update_techtree.py
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

USER_AGENT = "aoe2-counter-overlay/0.1 (personal overlay project)"
BASE = "https://raw.githubusercontent.com/SiegeEngineers/aoe2techtree/master/"
FILES = {
    "data/data.json": "data.json",
    "data/locales/en/strings.json": "strings_en.json",
}

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "techtree"


def fetch(path: str) -> bytes:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src, dst in FILES.items():
        raw = fetch(src)
        json.loads(raw)  # only save valid JSON
        (OUT / dst).write_bytes(raw)
        print(f"{src} -> {OUT / dst} ({len(raw) // 1024} KB)")

    data = json.loads((OUT / "data.json").read_text(encoding="utf-8"))
    civs = sorted(data.get("civs", {}))
    print(f"\n{len(civs)} civs: {', '.join(civs)}")
    print("Now run tools\\check_data.py – new civs need an entry in data\\civ_tips.en.json.")


if __name__ == "__main__":
    main()
