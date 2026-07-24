"""HTTP client for the HackTheBox Academy API.

Endpoint layout (all GET, no request body), confirmed against two open-source
references (Tut-k0/htb-academy-to-md and 0xca1x/htb-academy-md):

    GET /api/v2/modules/{module_id}                          # module metadata
    GET /api/v3/modules/{module_id}/sections                 # section list  (note: v3)
    GET /api/v2/modules/{module_id}/sections/{section_id}    # section content

Every response is wrapped as {"data": ...}; this client unwraps it for you.

Auth is cookie-based (programmatic login is blocked by reCAPTCHA/2FA). The
caller supplies the raw Cookie header string, which must include at least
`htb_academy_session=...`. A per-module Referer is mandatory for the API to
cooperate, so set_referer(module_id) is called automatically on each request.
"""

from __future__ import annotations

import requests


HTB_BASE = "https://academy.hackthebox.com"

# Image paths that start with "/content/" are served from the CDN host.
CDN_BASE = "https://cdn.services-k8s.prod.aws.htb.systems"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)


class HTBAuthError(RuntimeError):
    """Raised when the cookie is missing/rejected (HTTP 401/403 or login redirect)."""


class HTBNotFoundError(RuntimeError):
    """Raised when a module or section does not exist or is not accessible."""


class HTBAPIError(RuntimeError):
    """Any other unexpected response from the Academy API."""


class HTBClient:
    def __init__(self, cookie: str, timeout: int = 30):
        self.cookie = cookie.strip()
        self.timeout = timeout
        self._session = requests.Session()
        self._referer = f"{HTB_BASE}/app/dashboard"

    # -- public API ---------------------------------------------------------

    def set_referer(self, module_id: int | str) -> None:
        """Point subsequent requests at this module's page (required by the API)."""
        self._referer = f"{HTB_BASE}/app/module/{module_id}"

    def get_module(self, module_id: int) -> dict:
        return self._get(f"/api/v2/modules/{module_id}")

    def get_sections(self, module_id: int) -> list[dict]:
        """Return a flat, ordered list of sections.

        The raw response groups sections (e.g. theory vs. assessment). We flatten
        it into a single list and sort by the `page` field so ordering matches
        the website regardless of how HTB groups them.
        """
        data = self._get(f"/api/v3/modules/{module_id}/sections")
        flat: list[dict] = []
        idx = 1
        for group in data or []:
            group_name = group.get("group", "") if isinstance(group, dict) else ""
            for s in (group.get("sections", []) if isinstance(group, dict) else []):
                flat.append(
                    {
                        "id": s["id"],
                        "title": s.get("title", f"Section-{idx}"),
                        "type": s.get("type", ""),
                        "group": group_name,
                        "page": s.get("page", idx),
                    }
                )
                idx += 1
        # `page` gives canonical cross-group ordering on the live site.
        flat.sort(key=lambda s: (s.get("page", 0), s["id"]))
        # Re-number 1..N after sorting.
        for i, s in enumerate(flat, 1):
            s["num"] = i
        return flat

    def get_section_content(self, module_id: int, section_id: int) -> dict:
        return self._get(
            f"/api/v2/modules/{module_id}/sections/{section_id}"
        )

    def get_walkthrough(self, walkthrough_id: int) -> dict:
        """Fetch a module's skill-assessment walkthrough (the 'Show solution'
        content). Returns the data dict with at least: id, module_id,
        instructions (Markdown)."""
        return self._get(f"/api/v2/walkthroughs/{walkthrough_id}")

    # -- internals ----------------------------------------------------------

    def _get(self, path: str) -> dict | list:
        url = path if path.startswith("http") else HTB_BASE + path
        try:
            resp = self._session.get(
                url,
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
            raise HTBAPIError(f"Network error reaching {url}: {e}") from e

        # Auth failures: 401/403, or a redirect back to login.
        if resp.status_code in (401, 403):
            raise HTBAuthError(
                f"HTB rejected the request (HTTP {resp.status_code}). "
                "Your cookie is likely missing or expired — re-copy "
                "htb_academy_session from your browser."
            )
        if resp.is_redirect and "login" in resp.headers.get("Location", "").lower():
            raise HTBAuthError(
                "HTB redirected to the login page. Your cookie is missing or expired."
            )
        if resp.status_code == 404:
            raise HTBNotFoundError(f"HTB returned 404 for {url}")
        if not resp.ok:
            raise HTBAPIError(
                f"Unexpected HTTP {resp.status_code} from {url}: "
                f"{resp.text[:300]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            # Got HTML back instead of JSON -> usually a login redirect page.
            if "<html" in resp.text[:500].lower():
                raise HTBAuthError(
                    "HTB returned HTML instead of JSON — likely a login redirect. "
                    "Your cookie is missing or expired."
                ) from e
            raise HTBAPIError(f"Non-JSON response from {url}") from e

        # Every HTB Academy payload is {"data": ...}. Fall back to the whole
        # object if the wrapper is absent, so callers stay simple.
        return payload.get("data", payload)
