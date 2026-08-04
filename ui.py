"""Colored console output.

One function, `say()`, a drop-in for `print()`. It picks a color from the
line's existing leading glyph (→ ✓ • …) instead of making every call site pass
a style, so the scrapers' output strings stay plain text.

Rich is configured with markup=False and highlight=False on purpose: our lines
contain literal brackets (`[theory     ]`, `[!bash!]$`) that Rich would
otherwise try to parse as style tags. Rich also drops color automatically when
stdout isn't a TTY or NO_COLOR is set, so piping to a file stays clean.
"""

from __future__ import annotations

import sys

from rich.console import Console

_out = Console(markup=False, highlight=False)
_err = Console(markup=False, highlight=False, stderr=True)

# Leading glyph → style. Matched against the line with indentation stripped.
_GLYPH_STYLES = {
    "→": "bold cyan",
    "✓": "bold green",
    "✗": "bold red",
    "•": "white",
    "!": "bold yellow",
}


def _style_for(text: str) -> str | None:
    stripped = text.lstrip()
    if not stripped:
        return None
    style = _GLYPH_STYLES.get(stripped[0])
    if style:
        return style
    low = stripped.lower()
    if low.startswith(("error", "auth error", "not found", "api error")) or "error:" in low:
        return "bold red"
    if low.startswith(("warn", "skipped", "interrupted")):
        return "yellow"
    return None


def say(*args, file=None, **kwargs) -> None:
    """print()-compatible, colored by the line's leading glyph."""
    console = _err if file is sys.stderr else _out
    text = " ".join(str(a) for a in args)
    # soft_wrap: don't let Rich re-wrap at terminal width — plain print didn't,
    # and wrapping would break long paths/URLs mid-token.
    console.print(text, style=_style_for(text), soft_wrap=True, **kwargs)


def demo() -> None:
    for line in ["→ Fetching module 90 metadata…", "  ✓ wrote 01-Intro.md",
                 "  • 15 section(s)", "     1. [theory     ] Overview",
                 "  auth error: HTTP 401", "Interrupted."]:
        say(line)
    assert _style_for("→ x") == "bold cyan"
    assert _style_for("  ✓ x") == "bold green"
    assert _style_for("  auth error: 401") == "bold red"
    assert _style_for("     1. [theory] Overview") is None  # brackets untouched
    print("ui self-check passed")


if __name__ == "__main__":
    demo()
