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
    """Cookie missing/expired, or THM redirected to login."""


class THMNotFoundError(Exception):
    """Room slug returned 404."""


class THMAPIError(Exception):
    """Any other unexpected response from THM."""


class THMClient:
    """Minimal client for the TryHackMe rooms API."""

    def __init__(self, cookie: str, room_code: str, timeout: int = 30) -> None:
        self.cookie = cookie.strip()
        self.timeout = timeout
        self._session = requests.Session()
        # THM checks Referer; point it at the room page we're scraping.
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

    def _get_data(self, path: str, room_code: str, expect: type):
        """GET an endpoint and unwrap its `{"status": "success", "data": …}`
        envelope, checking `data` is the shape the caller expects."""
        payload = self._get_json(path, params={"roomCode": room_code})
        if payload.get("status") != "success":
            raise THMAPIError(f"THM {path} returned non-success status: {payload}")
        data = payload.get("data")
        if not isinstance(data, expect):
            raise THMAPIError(f"Unexpected THM {path} shape: {payload}")
        return data

    def get_room_info(self, room_code: str) -> dict:
        """Room metadata: title, description, difficulty, creators."""
        return self._get_data("/api/v2/rooms/details", room_code, dict)

    def get_room_tasks(self, room_code: str) -> list[dict]:
        """Task list — each has taskNo, title, description (HTML), questions."""
        return self._get_data("/api/v2/rooms/tasks", room_code, list)
