# AoE2 Konter-Overlay

Persönliches Hilfs-Overlay für Age of Empires II: Definitive Edition. Es zeigt beim Spielstart automatisch, welche Zivilisationen die Gegner spielen, was diese können und wie man sich am besten dagegen wehrt. Nur für einen Nutzer (Jannik), nur auf seinem Windows-PC. Sprache der Oberfläche, aller Inhalte, des Codes und der Antworten an Jannik: **Englisch** (Einheitennamen wie im englischen Spielclient).

## Rahmenbedingungen

* Windows 11, AoE2 DE über Steam.
* Eigenes Spielerprofil auf aoe2companion: `profile\_id = 21339043` (Name „\[Mosel] Sir Fboard“).
* Gespielt werden fast nur **Teamspiele** (2v2 bis 4v4, auch ungleiche Teams wie 3v2) in **Unranked-Lobbys** mit einer festen Gruppe, Karten v. a. Arena, Arabia und die Custom-Karte „Rage Forest“. Gelegentlich Team-Ranked.

## Datenquelle: aoe2companion-API

Offizielle Doku: https://www.aoe2companion.com/more/api – Nutzungsregeln einhalten:

* Bei jedem Aufruf einen User-Agent mit Projektnamen bzw. -URL setzen.
* Keine überflüssigen Aufrufe, kein Massenabruf.

Zugänge:

* **Bevorzugt Websocket für laufende Spiele:** `wss://socket.aoe2companion.com/listen?handler=ongoing-matches\&profile\_ids=21339043`
* **Fallback Polling** (nur falls der Websocket nicht funktioniert, höchstens alle 30 s): `https://data.aoe2companion.com/api/matches?profile\_ids=21339043\&use\_enums=true\&page=1\&per\_page=1`
* Das Nachrichtenformat des Websockets ist nicht dokumentiert. **Erster Schritt: mit einem kleinen Testskript mitschneiden, was während eines echten Spielstarts ankommt**, und das Format in `docs/api-notes.md` festhalten, bevor die App darauf aufbaut.

Benötigt werden pro Spieler: Name, `profile\_id`, Zivilisation, Team. Eigenes Team = Team von `profile\_id 21339043`, alle anderen Teams = Gegner.

## Zivilisationsdaten

* Basisdaten aus dem Community-Techbaum: Repository `SiegeEngineers/aoe2techtree` (Datei `data/data.json` plus englische Texte aus `data/locales/en/strings.json`). Daraus: Spezialeinheiten, Spezialtechnologien, Zivilisationsboni, Teambonus, vollständiger Techbaum.
* **Techbaum-Lücken automatisch ableiten:** z. B. „keine Paladine“, „kein Arbalestier“, „keine Belagerungsramme“, fehlende Schmiede-Upgrades. Das sind die wichtigsten Schwachstellen.
* Neue Civs aus aktuellen DLCs müssen enthalten sein. Den Datenstand beim Bauen prüfen und ein einfaches Update-Skript vorsehen.

## Strategie- und Konter-Inhalte

**Grundregel: keine frei erfundenen Ratschläge.** Zielgruppe ist ein eher neuer Spieler gegen erfahrenere Gegner; falsche Tipps schaden mehr als fehlende.

* **Konter werden berechnet, nicht geschrieben** (`aoe2overlay/counters.py`): Schlüsseleinheiten jeder Gegner-Civ (Spezialeinheiten + im offiziellen Civ-Text genannte Einheitentypen), deren offizielle In-Game-Texte „Strong vs./Weak vs.“ und die Techbäume ergeben „deren Einheit → deine Antwort“ (höchste Stufe, die die eigene Civ bauen kann). Fehlende Unit-Texte werden aus den lokalen Spieldateien ergänzt (`tools/update_maps.py` → `data/unit_texts_game.json`).
* „Good picks“: eigene Einheiten, deren spezifische Konter (z. B. Halberdier, Heavy Camel, Elite Skirmisher) keiner der Gegner voll ausbauen kann.
* `data/civ\_tips.en.json` enthält nur noch belegte Notizen: `profile`, `dangers` (was/wann), `sources`, `checked`. Grundlage: Civ-Strategieseiten des Age of Empires Series Wiki (fandom). Konter/Schwächen dort nicht von Hand eintragen – `tools/check_data.py` schlägt sonst fehl.
* Karten: offizielle Kurzbeschreibung aus den Spieldateien (`data/maps_official.json`) plus belegte Notizen in `data/maps.en.json` (Startressourcen, Zusatzressourcen, 2–3 Tipps, Quellen). Rage Forest = Community-Variante von Black Forest.

## Team-Analyse

Über alle Gegner zusammen (berechnet in `aoe2overlay/analysis.py`):

* „Build“: die 2–3 eigenen Einheiten, die die meisten gegnerischen Schlüsseleinheiten kontern.
* „Good picks“ und gegnerische Einheiten ohne direkten Konter im eigenen Techbaum.
* Gemeinsame Techbaum-Lücken der Gegner (z. B. „no Knights (2/3)“), nur aus den Techbäumen berechnet.
* Gegnerischen Teambonus nur in der Detailansicht je Civ anzeigen (meist nicht spielentscheidend, daher nicht in der Kompaktansicht).
* Eigene Civ berücksichtigen: Kompaktansicht eine Zeile „You: …“ mit eigenen Lücken, Detailansicht kleine Karte; Konter werden immer für die eigene Civ berechnet.

## Oberfläche

* Kleines Fenster, **immer im Vordergrund**, halbtransparent, frei positionierbar. Position und Größe werden gespeichert.
* Hotkey zum Ein- und Ausblenden (Standard F9, konfigurierbar), zweiter Hotkey zum Umschalten Kompakt/Detail (Standard Shift+F9), dritter Hotkey Sperren/Klick-durch (Standard Ctrl+F9). Die gebundenen Tasten werden unter Windows **abgefangen** und erreichen das Spiel nicht (F9 öffnet in AoE2 sonst die Hotkey-Übersicht, F10 das Spielmenü); alle anderen Tasten gehen normal durch.
* Schriftgröße per Strg+Mausrad, Civ-Icons (aoe2companion-CDN, lokal gecacht), Linkleiste (Map · Gegner | You · Verbündete), Spielerfarben und Ratings.
* **Kompaktansicht:** pro Gegner eine Zeile mit Spielername, Civ, Spezialeinheit und dem wichtigsten Konter-Stichwort, darunter die Team-Empfehlungen.
* **Detailansicht:** volle Karte pro Gegner-Civ.
* Erscheint automatisch beim Spielstart und blendet nach dem Spiel aus.
* Hinweis an den Nutzer: Overlays sind nur sichtbar, wenn AoE2 im Modus **„Vollbild (Fenster)“ / randlos** läuft, nicht im exklusiven Vollbild.

## Technik

* Python 3.12, PySide6 für das Fenster, `websockets` für den Live-Kanal.
* Globale Hotkeys über die Windows-API `RegisterHotKey` (`aoe2overlay/hotkeys.py`, kein Keyboard-Hook, kein pynput): Windows meldet nur die gebundenen Kombinationen und hält sie vom Spiel fern.
* Benutzerdaten in `%APPDATA%\AoE2CounterOverlay`: `config.json` (profile_id, Hotkeys, Transparenz, Position, `hide_after_game_s`), `overlay.log`, `socket-raw.log` (alle Live-Nachrichten), Icon-Cache. Mitgelieferte Daten (`data/`) liegen in der .exe.
* Paketierung: `build_exe.bat` (PyInstaller, eine `.exe` in `dist/`), Start aus dem Quellcode mit `start.bat` / `demo.bat`. Autostart optional über das Tray-Menü (HKCU-Run-Eintrag, nur für die .exe).
* Tray-Menü: Ein/Aus, Kompakt/Detail, Sperren, Demo, letztes Match, Einstellungsordner, Mit Windows starten, Beenden.

## Testmodus

* `--demo`: lädt ein fest hinterlegtes Beispiel-Match, z. B. 3v3 Rage Forest gegen Bulgaren, Bengalen und Inka, damit die Oberfläche ohne laufendes Spiel testbar ist.
* `--last-match`: holt das letzte echte Match per API und zeigt es an.

## Meilensteine

1. API-Testskript: Websocket mitschneiden, Format dokumentieren.
2. Datenschicht: Civ-Daten laden, Techbaum-Lücken berechnen, `civ\_tips.en.json` für alle Civs entwerfen.
3. Overlay-Fenster mit Demo-Daten und Hotkeys.
4. Live-Anbindung: Overlay reagiert auf echten Spielstart.
5. Team-Analyse.
6. `.exe` bauen, Kurzanleitung in `README.md`.

## Abnahme

* Bei einem echten Lobby-Spiel erscheinen spätestens wenige Sekunden nach Spielstart alle Gegner mit korrekter Civ.
* Hotkey blendet zuverlässig ein und aus, ohne das Spiel zu stören.
* Funktioniert mit 1–7 Gegnern und mit KI-Spielern im Gegnerteam (KI = Civ anzeigen, kein Name).

