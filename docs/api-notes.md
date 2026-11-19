# aoe2companion API – notes

As of 2026-11-12. User-Agent on every request: `aoe2-counter-overlay/0.1 (personal overlay project)`.

## Websocket `ongoing-matches` (primary live channel)

`wss://socket.aoe2companion.com/listen?handler=ongoing-matches&profile_ids=21339043`

Recorded with `tools/ws_capture.py` during two real games on 2026-11-12
(`captures/ws_20261112_091306.jsonl`: 1v1 vs AI, `captures/ws_20261112_131052.jsonl`: 2v2 with AI ally vs 2 AI).

### Messages

Every message is a **JSON list of events**:

```json
[]                                                     // right after connecting: no ongoing match
[{"type": "matchAdded",   "data": { …match… }}]        // game started
[{"type": "matchRemoved", "data": {"matchId": 520580689}}]  // game ended
```

* No authentication. The server pushes events; nothing needs to be sent. Ping/pong of the websocket library keeps the connection alive.
* The `matchAdded` match object has the same top-level fields as the REST API (`matchId`, `started`, `finished: null`, `map`, `mapName`, `leaderboardId`, `hideCivs`, …) **but players are a flat list `players[]`** instead of `teams[].players[]`. Each player has `team`, `teamName` and additional fields (`rating`, `games`, `steamId`, …).
* Player fields used: `profileId`, `name`, `civ` (lowercase enum), `team`, `status` (`"player"` / `"ai"`).
* AI players: `profileId: -1`, `name: "AI"`, `status: "ai"`, `steamId: null`.
* Team numbers are arbitrary (1/2, 5/6 seen). Only compare for equality.

### Timing

| Game | `started` (UTC) | `matchAdded` received | `finished` (REST) | `matchRemoved` received |
|---|---|---|---|---|
| 1v1 vs AI | 08:14:42 | 08:15:13 (+31 s) | 08:26:01 | 08:26:15 (+14 s) |
| 2v2 with AI | 12:12:07 | 12:12:17 (+10 s) | – | 12:14:49 |

So the overlay can show the opponents roughly 10–30 s after the game starts and hide ~15 s after it ends.

### Not yet observed

* What the first message looks like if you connect **while** a game is running (probably a list with `matchAdded`, or plain match objects). The client accepts both.
* Other event types (e.g. `matchUpdated`). The client treats any event with a match object in `data` like `matchAdded`.

## REST `matches` (fallback and `--last-match`)

`https://data.aoe2companion.com/api/matches?profile_ids=21339043&use_enums=true&page=1&per_page=1`

Sample: `captures/last_match_sample.json`. Relevant fields:

```
matches[0]
  matchId, started, finished (null while running), leaderboardId ("unranked" …)
  map, mapName, hideCivs
  teams[]
    teamId
    players[]
      profileId, name, civ (enum, e.g. "malay"), civName ("Malay")
      team, color, colorHex, slot, status ("player"/"ai"), rating, won
```

* `civ` is a lowercase English enum key; matched case-insensitively against aoe2techtree civ keys (`civdata.find_civ`).
* Own team = team containing `profileId == 21339043`, all other teams = opponents.
* `hideCivs: true` → civs may be hidden; the overlay then shows "Civ hidden".
* Polling is only used if the websocket keeps failing, at most every 30 s. A match counts as running when `finished` is null and `started` is less than 3 hours ago.
