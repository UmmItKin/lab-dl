"""Fetch a TryHackMe room through a real browser, to clear Vercel BotID.

TryHackMe gates its room API behind Vercel BotID, a JavaScript challenge no
HTTP client can pass (see thm_api). A patched Chromium loads the room page,
the challenge clears, then we `fetch` the two API endpoints from inside that
page context so they carry the live clearance. Needs a display (headed); on a
headless box wrap the command in xvfb-run.
"""

from __future__ import annotations

import time
from pathlib import Path

from ui import say

_ROOM_URL = "https://tryhackme.com/room/{}"
_UDD = Path.home() / ".cache" / "lab-dl" / "thm-chromium"


def _connect_sid(cookie_header: str) -> str:
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("connect.sid="):
            return part[len("connect.sid="):]
    return ""


def fetch_room(room_code: str, cookie_header: str, timeout: int = 60) -> tuple[dict, list]:
    """Return (details, tasks) for a room, unwrapped from the API envelope."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "patchright is needed to get past TryHackMe's bot check.\n"
            "  uv add patchright && uv run patchright install chromium"
        )

    sid = _connect_sid(cookie_header)
    _UDD.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(_UDD), channel="chromium", headless=False, no_viewport=True
        )
        try:
            if sid:
                ctx.add_cookies([{"name": "connect.sid", "value": sid,
                                  "url": "https://tryhackme.com"}])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            say(f"→ Opening {room_code!r} in a browser to clear the bot check…")
            page.goto(_ROOM_URL.format(room_code), wait_until="domcontentloaded",
                      timeout=timeout * 1000)
            for _ in range(timeout):
                if "Security Checkpoint" not in page.title():
                    break
                time.sleep(1)
            else:
                raise SystemExit(
                    "Vercel checkpoint never cleared. Try again, or run headed "
                    "on a machine with a display."
                )

            data = page.evaluate(
                """async (room) => {
                    const get = async (ep) => {
                        const r = await fetch(`/api/v2/rooms/${ep}?roomCode=${room}`,
                                              {headers: {Accept: 'application/json'}});
                        if (!r.ok) throw new Error(`${ep} HTTP ${r.status}`);
                        return (await r.json()).data;
                    };
                    return {details: await get('details'), tasks: await get('tasks')};
                }""",
                room_code,
            )
        finally:
            ctx.close()

    return data["details"], data["tasks"]
