"""One place to get a room's data, whichever transport works.

Tries the HTTP API first; on a Vercel BotID 429 it falls back to the browser
(thm_browser). Auth and not-found errors pass straight through so the caller
keeps its exit codes. thm_browser is imported lazily so patchright stays
optional, the same pattern as cookiejar.
"""

from __future__ import annotations

from thm_api import THMAPIError, THMClient
from ui import say


def fetch_room(room_code: str, cookie: str, timeout: int = 30) -> tuple[dict, list]:
    """Return (details, tasks) for a room. Raises THMAuthError / THMNotFoundError."""
    client = THMClient(cookie=cookie, room_code=room_code, timeout=timeout)
    try:
        return client.get_room_info(), client.get_room_tasks()
    except THMAPIError as e:
        if "429" not in str(e):
            raise
        say("• API blocked by Vercel BotID (HTTP 429); falling back to a browser.")
        import thm_browser
        return thm_browser.fetch_room(room_code, cookie, timeout)
