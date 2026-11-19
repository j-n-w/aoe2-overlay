"""Live feed: reports game start/end for the own profile.

Primary: aoe2companion websocket (see docs/api-notes.md for the message format).
Fallback: REST polling every 30 s while the websocket keeps failing.
ReplayFeed plays back a capture file from tools/ws_capture.py for testing.

Feeds run in a background thread and talk to the GUI only through Qt signals.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import pathlib
import threading
import time
import urllib.request

import websockets
from PySide6.QtCore import QObject, Signal

from .logs import raw_log
from .match import API_MATCHES, USER_AGENT, Match, parse_match

log = logging.getLogger(__name__)

WS_URL = "wss://socket.aoe2companion.com/listen?handler=ongoing-matches&profile_ids={pid}"
POLL_INTERVAL = 30          # seconds, API rules: no more often than this
WS_FAILS_BEFORE_POLL = 3    # consecutive failed connects before switching to polling
POLL_PHASE = 300            # seconds of polling before trying the websocket again
RUNNING_MAX_AGE = 3 * 3600  # REST: a match without "finished" older than this is ignored
SNAPSHOT_GRACE = 3.0        # seconds to wait for the running match after a reconnect snapshot


class _Feed(QObject):
    match_started = Signal(object)   # Match
    match_ended = Signal(object)     # match id (int) or None
    status = Signal(str)

    def __init__(self, profile_id: int):
        super().__init__()
        self.profile_id = profile_id
        self.current_id: int | None = None
        self._pending_end: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    # ---- shared message handling -------------------------------------------------
    def handle_message(self, raw: str, snapshot: bool = False) -> None:
        """Processes one websocket message. snapshot=True for the first message after connecting."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        events = data if isinstance(data, list) else [data]

        seen_ids: set[int] = set()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            etype = str(ev.get("type", "")).lower()
            payload = ev.get("data") if "data" in ev else ev
            if not isinstance(payload, dict):
                continue
            mid = payload.get("matchId")
            if "removed" in etype or (payload.get("finished") and mid == self.current_id):
                self._end(mid)
                continue
            if payload.get("players") or payload.get("teams"):
                match = parse_match(payload, self.profile_id)
                if match.me is None:
                    continue  # not our game
                seen_ids.add(match.match_id)
                self._start(match)

        # Snapshot after (re)connect: the server first sends [] and then, right after, the running
        # match as matchAdded. So a shown match missing from the snapshot only counts as ended if it
        # isn't re-added within SNAPSHOT_GRACE seconds (see check_pending_end).
        if snapshot and self.current_id is not None and self.current_id not in seen_ids:
            self._pending_end = time.monotonic() + SNAPSHOT_GRACE
        elif seen_ids:
            self._pending_end = None

    def check_pending_end(self) -> None:
        if self._pending_end is not None and time.monotonic() >= self._pending_end:
            self._pending_end = None
            self._end(self.current_id)

    def _start(self, match: Match) -> None:
        if match.match_id != self.current_id:
            log.info("match %s started: %s", match.match_id, match.title)
        self.current_id = match.match_id
        self.match_started.emit(match)

    def _end(self, mid) -> None:
        if self.current_id is not None and (mid is None or mid == self.current_id):
            log.info("match %s ended", self.current_id)
            self.current_id = None
            self.match_ended.emit(mid)


class LiveFeed(_Feed):
    def _run(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        fails = 0
        while not self._stop.is_set():
            if fails >= WS_FAILS_BEFORE_POLL:
                await self._poll_phase()
                fails = 0
                continue
            try:
                await self._websocket()
                fails = 0
            except Exception as e:  # network errors, server closing, invalid handshake …
                fails += 1
                log.warning("websocket: %r", e)
                self.status.emit(f"Live connection lost ({type(e).__name__}), retrying …")
                await self._sleep(min(5 * fails, 30))

    async def _websocket(self) -> None:
        url = WS_URL.format(pid=self.profile_id)
        async with websockets.connect(url, user_agent_header=USER_AGENT, ping_interval=20,
                                      open_timeout=15, max_size=None) as ws:
            self.status.emit("Waiting for game start …")
            first = True
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    self.check_pending_end()
                    continue
                raw = msg if isinstance(msg, str) else msg.decode("utf-8", "replace")
                raw_log.info("WS %s", raw[:20000])
                self.handle_message(raw, snapshot=first)
                first = False

    async def _poll_phase(self) -> None:
        self.status.emit("Live connection unavailable – polling every 30 s")
        end = time.monotonic() + POLL_PHASE
        while not self._stop.is_set() and time.monotonic() < end:
            try:
                await asyncio.to_thread(self._poll_once)
            except Exception as e:
                self.status.emit(f"Polling failed ({type(e).__name__})")
            await self._sleep(POLL_INTERVAL)

    def _poll_once(self) -> None:
        req = urllib.request.Request(API_MATCHES.format(pid=self.profile_id), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        raw_log.info("REST %s", json.dumps(data)[:20000])
        matches = data.get("matches") or []
        if not matches:
            return
        m = matches[0]
        running = not m.get("finished") and _age_seconds(m.get("started")) < RUNNING_MAX_AGE
        if running and m.get("matchId") != self.current_id:
            self._start(parse_match(m, self.profile_id))
        elif not running and self.current_id == m.get("matchId"):
            self._end(self.current_id)

    async def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < end:
            await asyncio.sleep(0.5)


class ReplayFeed(_Feed):
    """Plays back a ws_capture JSONL file; gaps between messages are shortened to max_gap seconds."""

    def __init__(self, profile_id: int, path: str, max_gap: float = 3.0):
        super().__init__(profile_id)
        self.path = pathlib.Path(path)
        self.max_gap = max_gap

    def _run(self) -> None:
        self.status.emit(f"Replaying {self.path.name} …")
        last_ts = None
        first = True
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if self._stop.is_set():
                return
            if not line.strip():
                continue
            rec = json.loads(line)
            ts = dt.datetime.fromisoformat(rec["ts"])
            if last_ts is not None:
                time.sleep(min((ts - last_ts).total_seconds(), self.max_gap))
            last_ts = ts
            self.handle_message(rec["raw"], snapshot=first)
            self.check_pending_end()
            first = False
        time.sleep(SNAPSHOT_GRACE)
        self.check_pending_end()
        self.status.emit("Replay finished")


def _age_seconds(iso: str | None) -> float:
    if not iso:
        return float("inf")
    started = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
