"""Extracts the official one-line map descriptions from the local AoE2 DE installation.

Reads resources/en/strings/key-value/key-value-strings-utf8.txt from the game
folder (found via Steam's registry entry, or pass --game-dir) and writes
data/maps_official.json: {"Arabia": "Arid desert with strategic elevations …", …}.

Usage:
    .venv\\Scripts\\python.exe tools\\update_maps.py [--game-dir "C:\\Games\\Steam\\steamapps\\common\\AoE2DE"]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "maps_official.json"
STRINGS = pathlib.Path("resources/en/strings/key-value/key-value-strings-utf8.txt")


def find_game_dir() -> pathlib.Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = pathlib.Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return None
    libs = [steam]
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        libs += [pathlib.Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8", "replace"))]
    for lib in libs:
        cand = lib / "steamapps" / "common" / "AoE2DE"
        if (cand / STRINGS).exists():
            return cand
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir")
    args = ap.parse_args()
    game = pathlib.Path(args.game_dir) if args.game_dir else find_game_dir()
    if not game or not (game / STRINGS).exists():
        sys.exit("AoE2 DE installation not found – pass --game-dir")

    names: dict[str, str] = {}
    descs: dict[str, str] = {}
    for line in (game / STRINGS).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'^(\d+)\s+"(.*)"\s*$', line)
        if not m:
            continue
        sid, text = int(m.group(1)), m.group(2)
        # map names live around 10800-11999, descriptions "Name - text" around 30100-30999
        if 10800 <= sid < 12000 and len(text) < 40:
            names[text] = text
        elif 30100 <= sid < 31000 and " - " in text:
            name, desc = text.split(" - ", 1)
            if name in names or len(name) < 30:
                descs[name.strip()] = desc.strip().replace("\\n", " ")
    OUT.write_text(json.dumps(dict(sorted(descs.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(descs)} map descriptions -> {OUT}")
    extract_unit_texts(game)


UNIT_OUT = ROOT / "data" / "unit_texts_game.json"


def extract_unit_texts(game: pathlib.Path) -> None:
    """Unit names/help texts the aoe2techtree strings lack (newer units like the Ratha)."""
    data = json.loads((ROOT / "data" / "techtree" / "data.json").read_text(encoding="utf-8"))
    tt = json.loads((ROOT / "data" / "techtree" / "strings_en.json").read_text(encoding="utf-8"))
    game_strings: dict[int, str] = {}
    for line in (game / STRINGS).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'^(\d+)\s+"(.*)"\s*$', line)
        if m:
            game_strings[int(m.group(1))] = m.group(2).replace("\\n", "\n")
    helps = [t for t in game_strings.values() if t.startswith("Create <b>") or t.startswith("Build <b>")]

    used = {u for c in data["civs"].values() for u in c["Unit"]}
    out: dict[str, dict] = {}
    for uid in sorted(used):
        u = data["data"]["Unit"][str(uid)]
        ln = u["LanguageNameId"]
        if tt.get(str(ln + 9000)) and tt.get(str(ln + 21000)):
            continue
        name = game_strings.get(ln) or game_strings.get(ln + 9000)
        if not name:
            continue
        base = re.sub(r"\s*\(.*\)$", "", name)          # "Ratha (Ranged)" -> "Ratha"
        help_ = next((h for h in helps if re.match(r"(Create|Build) <b>" + re.escape(base) + r"<", h)), "")
        out[str(uid)] = {"name": base, "help": help_}
    UNIT_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out)} unit texts from the game files -> {UNIT_OUT}: {', '.join(v['name'] for v in out.values())}")


if __name__ == "__main__":
    main()
