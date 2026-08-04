"""Auto-grab HackTheBox Academy cookies from a local Firefox-based browser.

This lets the scraper run without a manually-maintained cookies.txt: if no
cookie file is present (or --reload-cookie is passed), we scan the user's
Firefox-based browser profiles (Floorp, Firefox, LibreWolf, Zen, Waterfox…),
find the one whose session is actually logged in to HTB Academy, and read the
`htb_academy_session` cookie directly from its cookies.sqlite.

Firefox-based browsers store cookie values in plaintext (unlike Chromium,
which encrypts them), so no keychain/key4.db decryption is needed — the
extraction is a plain sqlite read, wrapped by browser_cookie3 which also
handles session-store recovery for cookies not yet flushed to disk.

This module never imports htb_scraper (keeps the import graph clean). It talks
to the network only via browser_cookie3's sqlite reads.
"""

from __future__ import annotations

import os
from pathlib import Path

from ui import say

# browser_cookie3 is the only third-party dep here. Imported lazily inside
# grab_htb_cookie() so that `import cookiejar` never hard-fails if the package
# is absent — callers get a clear error only when they actually try to grab.

# The cookie the scraper needs to authenticate to the Academy API.
TARGET_COOKIE_NAME = "htb_academy_session"
TARGET_DOMAIN = "hackthebox.com"

# Firefox-based browser profile roots on Linux/macOS/Windows. We scan ALL of
# these and, within each, every profile directory — the one HTB is logged in
# to may not be profiles.ini's "Default" (e.g. a user's daily profile vs. a
# clean test profile), so trusting Default= is unreliable. Scanning is cheap.
_FIREFOX_BASE_DIRS = {
    "linux": [
        "~/.floorp",            # Floorp
        "~/.waterfox",
        "~/.librewolf",
        "~/.zen",
        "~/.bunfofox",
        "~/.mozilla/firefox",   # vanilla Firefox (checked last as a fallback)
        "~/snap/firefox/common/.mozilla/firefox",
    ],
    "darwin": [
        "~/Library/Application Support/Floorp",
        "~/Library/Application Support/Waterfox",
        "~/Library/Application Support/LibreWolf",
        "~/Library/Application Support/zen",
        "~/Library/Application Support/Firefox",
    ],
    "win32": [
        "~/.floorp",            # portable installs
        "~/.waterfox",
        "~/.librewolf",
        "~/.zen",
        "~/AppData/Roaming/Mozilla/Firefox",
    ],
}


def _platform_dirs() -> list[str]:
    import sys

    for key in ("linux", "darwin", "win32"):
        if sys.platform == key or (key == "linux" and sys.platform.startswith("linux")):
            return _FIREFOX_BASE_DIRS[key]
    # BSD / other unix: try the linux paths as a best effort.
    return _FIREFOX_BASE_DIRS["linux"]


def _iter_cookie_databases() -> list[str]:
    """Return every cookies.sqlite path found under any known Firefox-based
    browser root. Excludes the chrome_debugger_profile (an empty clone Firefox
    makes for devtools)."""
    import glob

    seen: set[str] = set()
    out: list[str] = []
    for base in _platform_dirs():
        base_expanded = os.path.expanduser(base)
        if not os.path.isdir(base_expanded):
            continue
        for cookie_db in glob.glob(
            os.path.join(base_expanded, "**", "cookies.sqlite"), recursive=True
        ):
            if "chrome_debugger_profile" in cookie_db:
                continue
            # Normalise so duplicates across symlinked roots collapse.
            real = os.path.realpath(cookie_db)
            if real in seen:
                continue
            seen.add(real)
            out.append(cookie_db)
    return out


def _load_from_db(cookie_db: str, domain: str):
    """Open one Firefox cookies.sqlite via browser_cookie3 and return its
    CookieJar (filtered to domain). Raises on any error so the caller can skip
    the profile silently."""
    import browser_cookie3

    return browser_cookie3.FirefoxBased(
        browser_name="firefox-based",
        cookie_file=cookie_db,
        domain_name=domain,
    ).load()


def grab_cookie(
    cookie_name: str,
    domain: str,
    label: str = "the site",
    login_url: str = "",
    verbose: bool = True,
) -> str:
    """Scan local Firefox-based browser profiles and return the
    `<cookie_name>=<value>` header string for the given domain.

    `label` and `login_url` are used only to build helpful error messages
    (e.g. label="HTB Academy", login_url="https://academy.hackthebox.com").

    Raises SystemExit with a helpful message if browser_cookie3 is missing,
    no browser profile is found, or no profile is logged in to the target site.
    """
    try:
        import browser_cookie3  # noqa: F401
    except ImportError:
        raise SystemExit(
            "browser_cookie3 is not installed, which is needed to auto-grab "
            "cookies from your browser.\n"
            "  pip install browser_cookie3\n"
            "Or pass --cookie '...' / create cookies.txt manually."
        )

    dbs = _iter_cookie_databases()
    if not dbs:
        raise SystemExit(
            "No Firefox-based browser profile found (looked in: "
            + ", ".join(_platform_dirs())
            + ").\n"
            "Either install Floorp/Firefox/LibreWolf/Zen/Waterfox and log in to "
            f"{label}, or pass --cookie '...' / create cookies.txt manually."
        )
    if verbose:
        say(f"→ Scanning {len(dbs)} browser profile(s) for a {label} session…")

    last_error: Exception | None = None
    for db in dbs:
        try:
            cj = _load_from_db(db, domain)
        except Exception as e:  # profile locked / corrupt / unreadable
            last_error = e
            continue
        for c in cj:
            if c.name == cookie_name:
                if verbose:
                    profile = _profile_label(db)
                    say(f"  ✓ found {cookie_name} in {profile}")
                return f"{cookie_name}={c.value}"

    # Scanned every profile, none had the cookie.
    login_hint = f"Make sure you're logged in to {login_url} in your " if login_url else ""
    raise SystemExit(
        f"No {label} session found in any scanned browser profile.\n"
        f"{login_hint}browser, then re-run (or pass --reload-cookie to re-scan).\n"
        f"Scanned: {dbs}"
        + (f"\nLast profile error: {last_error}" if last_error else "")
    )


def grab_htb_cookie(verbose: bool = True) -> str:
    """Convenience wrapper for HackTheBox Academy (`htb_academy_session`)."""
    return grab_cookie(
        cookie_name=TARGET_COOKIE_NAME,
        domain=TARGET_DOMAIN,
        label="HTB Academy",
        login_url="https://academy.hackthebox.com",
        verbose=verbose,
    )


def grab_thm_cookie(verbose: bool = True) -> str:
    """Convenience wrapper for TryHackMe (`connect.sid`, an Express session)."""
    return grab_cookie(
        cookie_name="connect.sid",
        domain="tryhackme.com",
        label="TryHackMe",
        login_url="https://tryhackme.com",
        verbose=verbose,
    )


def _profile_label(cookie_db: str) -> str:
    """Human-readable label like 'floorp/fa7ii0bz.default-release'."""
    # cookie_db = .../.floorp/<profile>/cookies.sqlite
    parent = os.path.dirname(cookie_db)          # .../<profile>
    profile = os.path.basename(parent)            # <profile>
    browser_root = os.path.dirname(parent)        # .../.floorp
    browser = os.path.basename(browser_root)      # .floorp
    return f"{browser}/{profile}"


def save_to_cookie_file(cookie_header: str, path: str | os.PathLike = "cookies.txt") -> Path:
    """Write a cookie header string to cookies.txt (the file load_cookie reads).
    Used by --reload-cookie so subsequent runs can skip the browser scan."""
    p = Path(path)
    p.write_text(cookie_header + "\n", encoding="utf-8")
    return p
