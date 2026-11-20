# AoE2 Counter Overlay

A small always-on-top window for Age of Empires II: DE. When a game starts it shows each enemy's civ, their key units and what beats them, map notes, your own civ and your allies.

It only reads **public match data** from aoe2companion.com. It does not read game memory, send input to the game, or analyse the screen.

## Start

**Option A – the .exe (no Python needed):** download `AoE2-Counter-Overlay.exe` from the [latest release](https://github.com/j-n-w/aoe2-overlay/releases/latest) and double-click it. It sits as a yellow "C" in the tray (bottom right) and appears by itself when a game starts.

**Option B – from source** (also the way round Windows "Smart App Control", which blocks unsigned .exe files): download `AoE2-Counter-Overlay-source.zip` from the same release, install Python 3.12 (Microsoft Store, or python.org with **"Add python.exe to PATH"** ticked), unzip and double-click `start.bat`. The first run sets everything up (1–2 minutes). `demo.bat` shows a sample 3v3 match without a running game.

**First start:** the overlay asks who you are – pick your name from the Stammtisch list (age-stammtisch.de) or type your aoe2companion profile id or profile link. The tray menu shows who is set (*Player: <name> – change …*); click it to pick someone else, no restart needed.

**Important:** set AoE2 to **Windowed Fullscreen / borderless**. In exclusive fullscreen Windows can't draw anything on top of the game.

The overlay appears 10–30 seconds after the game starts (that's how long aoe2companion needs to see the match) and hides about 25 seconds after the game ends.

## Controls

| | |
|---|---|
| **F9** | show / hide |
| **Shift+F9** | compact ↔ detail view |
| **Ctrl+F9** | lock: clicks go through to the game (press again to unlock) |
| **Ctrl + mouse wheel** | font size |
| link bar at the top | jump to map, an enemy, you or an ally (switches to detail view) |
| drag anywhere | move the window |
| bottom-right corner | resize |
| tray icon, right-click | demo match, last match, *Player: … – change …*, settings folder, start with Windows, quit |

Bound keys are taken by the overlay and don't reach the game (F9 would otherwise open AoE2's hotkey list). If you need one of them in AoE2, choose another key in the settings.

## How to read it

* **Compact:** one block per enemy: `their unit → your answer`. Below that, **Build** lists your units that answer the most enemy units, "Good pick" units none of the enemies can fully counter, and gaps the enemy team shares.
* **Detail:** everything per enemy: profile, what to watch out for, key units with their official Strong/Weak vs. texts, what they lack, team bonus.

Counters are **computed** from the game's own unit texts and the tech trees, always for the civ you're playing. Notes (profile, dangers, map tips) come from the Age of Empires wiki and list their source.

## Settings

Tray → **Open settings folder** (`%APPDATA%\AoE2CounterOverlay`). `config.json` there:

| key | meaning |
|---|---|
| `profile_id` | your aoe2companion profile (0 = ask on next start) |
| `hotkey_toggle`, `hotkey_mode`, `hotkey_lock` | e.g. `"F9"`, `"shift+F9"`, `"ctrl+alt+o"`, `"pause"` |
| `hide_after_game_s` | seconds the overlay stays after the game ends |
| `opacity` | background opacity 0.0–1.0 |
| `font_size`, `compact`, `locked`, `geometry` | saved automatically |

Restart the overlay after editing (tray → Quit, then start again).

## Troubleshooting

* **Wrong player picked / overlay shows someone else's games:** tray → *Player: … – change …*. If the overlay doesn't start at all, set `profile_id` to `0` in `config.json` (or delete the file): it asks again on the next start.
* **Nothing appears at game start:** wait 30 s. Then tray → *Show last match*. If that works, the live connection is the problem – see `overlay.log`.
* **"Hotkey problem" in the window:** another program already uses that key. Pick another one in `config.json`.
* **Logs:** `overlay.log` (events, errors) and `socket-raw.log` (every message from aoe2companion) in the settings folder.
* **Second start does nothing:** only one overlay can run; look for the tray icon.

## Updating data (after an AoE2 patch / new civs)

```
.venv\Scripts\python.exe tools\update_techtree.py
.venv\Scripts\python.exe tools\update_maps.py
.venv\Scripts\python.exe tools\check_data.py
```

New civs get computed counters automatically; `tools\check_data.py` reports civs that are missing wiki notes. Then rebuild the .exe with `build_exe.bat`, or publish a release: raise the number in `VERSION` on main (e.g. `1.2`) and GitHub Actions builds the .exe and the source zip and attaches both to the release (`.github/workflows/build-exe.yml`).

## Development

* `python -m aoe2overlay --demo | --last-match | --detail | --replay captures\<file>.jsonl`
* `tools\ws_capture.py` records the live websocket; format in `docs\api-notes.md`.
* `python -m aoe2overlay.counters <your civ> <enemy civ> …` prints the computed counters.
