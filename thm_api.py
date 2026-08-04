"""TryHackMe API client.

Single endpoint: GET /api/v2/rooms/tasks?roomCode=<slug>
Returns the full task list for a room (descriptions + questions).

Auth: cookie-based (connect.sid session + _csrf). The Referer header is
required (same pattern as HTB). All requests are GET with no body.
"""

from __future__ import annotations

import requests

THM_BASE = "https://tryhackme.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


class THMAuthError(Exception):
    """Cookie missing/expired, or THB redirected to login."""


class THMNotFoundError(Exception):
    """Room slug returned 404."""


class THMAPIError(Exception):
    """Any other unexpected response from THM."""


class THMClient:
    """Minimal client for the TryHackMe rooms API."""

    def __init__(self, cookie: str, timeout: int = 30) -> None:
        self.cookie = cookie.strip()
        self.timeout = timeout
        self._session = requests.Session()
        self._referer = THM_BASE + "/"  # default; override per-room via set_referer

    def set_referer(self, room_code: str) -> None:
        """Point subsequent requests' Referer at a specific room page."""
        self._referer = f"{THM_BASE}/room/{room_code}"

    def _get_json(self, path: str, params: dict | None = None) -> dict | list:
        """Shared GET with auth/Referer/error handling. Returns parsed JSON."""
        url = THM_BASE + path
        try:
            resp = self._session.get(
                url,
                params=params,
                headers={
                    "Cookie": self.cookie,
                    "Accept": "application/json",
                    "Referer": self._referer,
                    "User-Agent": USER_AGENT,
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            raise THMAPIError(f"Network error reaching {url}: {e}") from e

        if resp.status_code in (401, 403):
            raise THMAuthError(
                f"THM rejected the request (HTTP {resp.status_code}). "
                "Your cookie is likely missing or expired — re-grab "
                "connect.sid (and _csrf) from your browser."
            )
        if resp.is_redirect and "login" in resp.headers.get("Location", "").lower():
            raise THMAuthError(
                "THM redirected to the login page. Your cookie is missing or expired."
            )
        if resp.status_code == 404:
            raise THMNotFoundError(f"THM returned 404 for {url}")
        if not resp.ok:
            raise THMAPIError(
                f"Unexpected HTTP {resp.status_code} from {url}: {resp.text[:300]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            if "<html" in resp.text[:500].lower():
                raise THMAuthError(
                    "THM returned HTML instead of JSON — likely a login redirect. "
                    "Your cookie is missing or expired."
                ) from e
            raise THMAPIError(f"Non-JSON response from {url}") from e

    def get_room_info(self, room_code: str) -> dict:
        """Fetch room metadata (title, description, difficulty, creators, etc.).
        Returns the `data` object from /api/v2/rooms/details?roomCode=."""
        payload = self._get_json("/api/v2/rooms/details", params={"roomCode": room_code})
        if payload.get("status") != "success":
            raise THMAPIError(f"THM rooms API returned non-success status: {payload}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise THMAPIError(f"Unexpected THM room info shape: {payload}")
        return data

    def get_room_tasks(self, room_code: str) -> list[dict]:
        """Fetch the task list for a room. Returns the `data` array
        (each task has taskNo, title, description (HTML), questions)."""
        payload = self._get_json("/api/v2/rooms/tasks", params={"roomCode": room_code})
        if payload.get("status") != "success":
            raise THMAPIError(f"THM tasks API returned non-success status: {payload}")
        data = payload.get("data")
        if not isinstance(data, list):
            raise THMAPIError(f"Unexpected THM response shape (data is not a list): {payload}")
        return data
