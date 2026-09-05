"""Top-level CLI: pick a platform, forward the rest to its scraper."""

from __future__ import annotations

import argparse

PLATFORMS = {"htb": "htb_scraper", "thm": "thm_scraper"}

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Download HackTheBox Academy modules and TryHackMe rooms "
        "as Markdown, for personal offline study.",
        epilog="Pass --help after the platform for that scraper's flags, "
        "e.g. `main.py htb --help`.",
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
