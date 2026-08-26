"""Top-level CLI: pick a platform, forward the rest to its scraper."""

from __future__ import annotations

import argparse

PLATFORMS = {"htb": "htb_scraper", "thm": "thm_scraper"}

_EPILOG = """\
examples:
  uv run python main.py htb 293               module by id or URL
  uv run python main.py htb path 419          whole path, then offer a .tar.xz
  uv run python main.py thm csrfintroduction  room by slug or URL
  uv run python main.py htb 293 --dry-run     check auth, write nothing

common flags:
  --cookie "..."      inline Cookie header
  --cookie-file PATH  read the Cookie header from a file
  --reload-cookie     re-grab the session cookie from your browser
  --output DIR        output directory (default: ./output)
  --timeout N         HTTP timeout in seconds (default: 30)
  --dry-run           list sections/tasks only, write nothing

htb extras:
  path <id>           download a whole job-role path (-y skips prompts)
  --no-walkthrough    skip the "Show solution" file
  --no-jitter         drop the polite sleep between sections
  --force             redownload path modules already on disk
  --debug-json        dump raw API JSON and exit

Logged in through a Firefox-based browser (Floorp, Firefox, LibreWolf, Zen,
Waterfox)? The session cookie is grabbed automatically. Otherwise pass
--cookie "..." or see cookies.txt.example.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Download HackTheBox Academy modules and TryHackMe rooms "
        "as Markdown, for personal offline study.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "platform",
        choices=PLATFORMS,
        metavar="{htb|thm}",
        help="htb = HTB Academy module or `path`; thm = TryHackMe room",
    )
    p.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        metavar="target [flags]",
        help="target and flags for the chosen platform (listed below)",
    )
    return p


def demo() -> None:
    ns = build_parser().parse_args(["htb", "293", "--dry-run"])
    assert ns.platform == "htb" and ns.rest == ["293", "--dry-run"], ns
    ns = build_parser().parse_args(["htb", "path", "419"])
    assert ns.rest == ["path", "419"], ns
    print("cli self-check passed")


if __name__ == "__main__":
    demo()
