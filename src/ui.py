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

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

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


def table(columns: list[str], rows: list[list], title: str | None = None) -> None:
    """Print a bordered table. Cells are rendered as plain text (no markup), so
    values containing brackets are safe."""
    t = Table(title=title, box=box.ROUNDED, header_style="bold cyan",
              title_style="bold", title_justify="left")
    for i, col in enumerate(columns):
        # First column is usually a number/id: right-align it, keep it narrow.
        t.add_column(col, justify="right" if i == 0 else "left", no_wrap=(i == 0))
    for row in rows:
        t.add_row(*("" if c is None else str(c) for c in row))
    _out.print(t)


def track(items, description: str):
    """Yield items behind a single self-updating progress bar.

    Replaces a per-item `say()` line, which turns a 317-section path run into a
    scrolling wall. Falls back to plain iteration when stdout isn't a TTY so
    logs and pipes stay readable.
    """
    if not _out.is_terminal:
        yield from items
        return
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=_out,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=len(items))
        for item in items:
            yield item
            progress.advance(task)


# Hardcoded wordmark: pyfiglet would be a whole dependency for one string.
_BANNER = r"""
██╗      █████╗ ██████╗   ██████╗ ██╗
██║     ██╔══██╗██╔══██╗  ██╔══██╗██║
██║     ███████║██████╔╝  ██║  ██║██║
██║     ██╔══██║██╔══██╗  ██║  ██║██║
███████╗██║  ██║██████╔╝  ██████╔╝███████╗
╚══════╝╚═╝  ╚═╝╚═════╝   ╚═════╝ ╚══════╝
"""


def banner(subtitle: str = "") -> None:
    """Print the lab-dl wordmark. Skipped on a non-TTY so logs stay clean."""
    if not _out.is_terminal:
        return
    art = Text(_BANNER.strip("\n"), style="bold green")
    if subtitle:
        art.append(f"\n {subtitle}", style="dim cyan")
    _out.print(Panel(art, box=box.ROUNDED, border_style="green", expand=False))


def rule(
    title: str,
    current: int | None = None,
    total: int | None = None,
    note: str = "",
) -> None:
    """One compact header per module in a path run: position, bar, then title.

    A full-width Rich rule plus a separate bar was too loud repeated 20 times,
    so this is a single line that still answers "where am I". The blocks here
    are deliberately not the `━` that `track()` uses, so the outer module bar
    can't be mistaken for the inner section bar.
    """
    if current is None or not total:
        # markup=False on the console, so pass the style, not inline tags.
        _out.rule(Text(title, style="bold cyan"), style="cyan")
        return
    width = 12
    done = round(width * current / total)
    line = Text()
    line.append(f"{current:>2}/{total} ", style="bold cyan")
    line.append("█" * done, style="green")
    line.append("░" * (width - done), style="bright_black")
    line.append(f"  {title}", style="dim" if note else "bold")
    if note:
        line.append(f"  ({note})", style="dim")
    _out.print(line)


def demo() -> None:
    banner("HTB Academy + TryHackMe -> Markdown")
    rule("289 Network Foundations", 2, 20)
    rule("34 Introduction to Networking", 3, 20, note="skipped")
    for line in ["→ Fetching module 90 metadata…", "  ✓ wrote 01-Intro.md",
                 "  • 15 section(s)", "     1. [theory     ] Overview",
                 "  auth error: HTTP 401", "Interrupted."]:
        say(line)
    assert _style_for("→ x") == "bold cyan"
    assert _style_for("  ✓ x") == "bold green"
    assert _style_for("  auth error: 401") == "bold red"
    assert _style_for("     1. [theory] Overview") is None  # brackets untouched
    table(["#", "Type", "Title"],
          [[1, "theory", "Overview"], [2, "interactive", "Pre-Engagement"]],
          title="Sections")
    assert list(track([1, 2, 3], "demo")) == [1, 2, 3]
    print("ui self-check passed")


if __name__ == "__main__":
    demo()
