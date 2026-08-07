"""Single entry point for both scrapers.

Usage:
    python main.py htb <module-id|url> [flags]
    python main.py thm <room-slug|url> [flags]

The library modules live in ./src/. Add that directory to sys.path so their
bare imports (`from htb_api import …`) resolve when this script runs from the
repo root, then dispatch the first argument to the matching scraper's main().
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# Subcommand → module. Loaded lazily so an `htb` run never imports thm_api and
# vice versa.
_PLATFORMS = {"htb": "htb_scraper", "thm": "thm_scraper"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: main.py {htb|thm} …\n"
            "  htb <module-id|url> [flags]   download a HackTheBox Academy module\n"
            "  thm <room-slug|url> [flags]   download a TryHackMe room\n"
            "\n"
            "Pass --help after the platform for that scraper's flags."
        )
        return 0
    platform, rest = args[0], args[1:]
    module_name = _PLATFORMS.get(platform)
    if module_name is None:
        print(
            f"unknown platform {platform!r}; expected one of: "
            + ", ".join(sorted(_PLATFORMS)),
            file=sys.stderr,
        )
        return 2
    module = importlib.import_module(module_name)
    return module.main(rest)


if __name__ == "__main__":
    sys.exit(main())
