"""Single entry point for both scrapers.

Usage:
    python main.py htb <module-id|url> [flags]
    python main.py thm <room-slug|url> [flags]

The library modules live in ./src/. Add that directory to sys.path so their
bare imports (`from htb_api import …`) resolve when this script runs from the
repo root, then hand off to cli.build_parser(), which picks the platform and
forwards the rest to that scraper's main().
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cli import PLATFORMS, build_parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv or "-h" in argv or "--help" in argv:
        parser.print_help()
        return 0
    ns = parser.parse_args(argv)
    from ui import banner
    banner("HTB Academy + TryHackMe -> Markdown")
    module = importlib.import_module(PLATFORMS[ns.platform])
    return module.main(ns.rest)


if __name__ == "__main__":
    sys.exit(main())
