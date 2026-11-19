"""Milestone 1: record the aoe2companion websocket for ongoing matches.

Connects to the ongoing-matches handler for the own profile and writes every
incoming message unchanged (with timestamp) to a JSONL file in captures/, so
the undocumented format can be analysed during a real game start.

Usage:
    .venv\\Scripts\\python.exe tools\\ws_capture.py            # runs until Ctrl+C
    .venv\\Scripts\\python.exe tools\\ws_capture.py --seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import pathlib
import sys

import websockets

PROFILE_ID = 21339043
USER_AGENT = "aoe2-counter-overlay/0.1 (personal overlay project)"
WS_URL = "wss://socket.aoe2companion.com/listen?handler=ongoing-matches&profile_ids={pid}"

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURE_DIR = ROOT / "captures"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


def summarize(raw: str) -> str:
    """Short console summary without assuming a format."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"(not JSON, {len(raw)} chars)"
    if isinstance(data, list):
        kinds = {type(x).__name__ for x in data}
        keys = sorted({k for x in data if isinstance(x, dict) for k in x})
        return f"list with {len(data)} entries ({', '.join(kinds)}), keys: {keys[:15]}"
    if isinstance(data, dict):
        return f"object, keys: {sorted(data)[:15]}"
    return f"{type(data).__name__}: {str(data)[:80]}"


async def capture(profile_id: int, seconds: float | None) -> None:
    CAPTURE_DIR.mkdir(exist_ok=True)
    out = CAPTURE_DIR / f"ws_{dt.datetime.now():%Y%m%d_%H%M%S}.jsonl"
    url = WS_URL.format(pid=profile_id)
    print(f"[{now()}] Connecting to {url}")
    print(f"[{now()}] Writing to {out}")

    async def run() -> None:
        backoff = 2
        while True:
            try:
                async with websockets.connect(
                    url, user_agent_header=USER_AGENT, ping_interval=20, max_size=None
                ) as ws:
                    print(f"[{now()}] Connected.")
                    backoff = 2
                    async for msg in ws:
                        raw = msg if isinstance(msg, str) else msg.decode("utf-8", "replace")
                        with out.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"ts": now(), "raw": raw}, ensure_ascii=False) + "\n")
                        print(f"[{now()}] Message ({len(raw)} chars): {summarize(raw)}")
            except (websockets.ConnectionClosed, OSError) as e:
                print(f"[{now()}] Connection lost ({e!r}), retrying in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    try:
        if seconds:
            await asyncio.wait_for(run(), timeout=seconds)
        else:
            await run()
    except asyncio.TimeoutError:
        print(f"[{now()}] Time limit {seconds}s reached, stopping.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile-id", type=int, default=PROFILE_ID)
    p.add_argument("--seconds", type=float, default=None, help="stop after N seconds")
    args = p.parse_args()
    try:
        asyncio.run(capture(args.profile_id, args.seconds))
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
