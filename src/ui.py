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
from datetime import datetime

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

# sqlmap colors the level tag and leaves the message plain; the tag alone tells
# you what kind of line it is.
_LEVEL_STYLES = {
    "DEBUG": "bright_black",
    "INFO": "bold blue",
    "ACTION": "bold cyan",
    "INPUT": "bold magenta",
    "SUCCESS": "bold green",
    "WARNING": "bold yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}

_out = Console(markup=False, highlight=False)
_err = Console(markup=False, highlight=False, stderr=True)

# Leading glyph → (sqlmap-style level, color). Call sites already start their
# lines with one of these, so the level is derived here instead of touching
# every say() in the scrapers.
_GLYPH_LEVELS = {
    "→": ("ACTION", None),
    "✓": ("SUCCESS", None),
    "✗": ("ERROR", None),
    "•": ("INFO", None),
    "!": ("WARNING", None),
}


def _classify(text: str) -> tuple[str | None, str | None, str]:
    """Split a message into (level, style, body). The body has the glyph and its
    indentation stripped, since the [LEVEL] tag replaces them."""
    stripped = text.lstrip()
    if not stripped:
        return None, None, text
    hit = _GLYPH_LEVELS.get(stripped[0])
    if hit:
        level, style = hit
        return level, style, stripped[1:].strip()
    low = stripped.lower()
    if low.startswith(("error", "auth error", "not found", "api error")) or "error:" in low:
        return "ERROR", None, stripped
    if low.startswith(("warn", "skipped", "interrupted")):
        return "WARNING", None, stripped
    return None, None, text


def say(*args, file=None, **kwargs) -> None:
    """print()-compatible. Renders sqlmap-style `[HH:MM:SS] [LEVEL] message`."""
    console = _err if file is sys.stderr else _out
    text = " ".join(str(a) for a in args)

    # Keep leading blank lines as spacing, but classify the message itself.
    lead = text[: len(text) - len(text.lstrip("\n"))]
    body_in = text[len(lead) :]
    level, style, body = _classify(body_in)

    if level is None:
        # No glyph and no error keyword: print as-is (tables, prompts, blanks).
        console.print(text, style=style, soft_wrap=True, **kwargs)
        return

    console.print(_tagged(level, body, lead, style), soft_wrap=True, **kwargs)


def _tagged(level: str, body: str, lead: str = "", style: str | None = None) -> Text:
    """`[HH:MM:SS] [LEVEL] body`. One space after the tag, never padding: lining
    the bodies up in a column reads like tab stops rather than a log."""
    line = Text(lead)
    line.append(f"[{datetime.now():%H:%M:%S}] ", style="bright_black")
    line.append(f"[{level}] ", style=_LEVEL_STYLES[level])
    line.append(body, style=style)
    return line


def ask(question: str) -> str:
    """Prompt with an [INPUT] tag, matching the log lines around it."""
    # Leading newlines are spacing from the call site; emit them before the tag
    # so the question stays on the same line as [INPUT].
    lead = question[: len(question) - len(question.lstrip("\n"))]
    question = question[len(lead) :]
    # Write the prompt ourselves and flush: Rich's print(end="") doesn't reliably
    # land before input() blocks, which left the question invisible.
    sys.stdout.write(
        f"{lead}\033[90m[{datetime.now():%H:%M:%S}]\033[0m "
        f"\033[1;35m[INPUT]\033[0m {question} "
    )
    sys.stdout.flush()
    try:
        return input()
    except EOFError:
        return ""


def table(columns: list[str], rows: list[list], title: str | None = None) -> None:
    """Print a bordered table. Cells are rendered as plain text (no markup), so
    values containing brackets are safe. The title is printed as a tagged log
    line rather than Rich's own title, so it matches the surrounding output."""
    if title:
        _out.print(_tagged("INFO", title), soft_wrap=True)
    t = Table(box=box.ROUNDED, header_style="bold cyan")
    for i, col in enumerate(columns):
        # First column is usually a number/id: right-align it, keep it narrow.
        t.add_column(col, justify="right" if i == 0 else "left", no_wrap=(i == 0))
    for row in rows:
        t.add_row(*("" if c is None else str(c) for c in row))
    _out.print(t)


def _progress_columns(tail):
    """Shared bar layout. The leading columns mimic a `[HH:MM:SS] [ACTION]` log
    line so a live bar sits in the same columns as the messages around it."""
    # No SpinnerColumn: the [ACTION] tag already marks this as work in progress,
    # and every extra column steals width from the bar itself.
    return [
        TextColumn("{task.fields[stamp]}", style="bright_black"),
        TextColumn("{task.fields[tag]}", style="bold cyan"),
        TextColumn("{task.description}", style="none"),
        BarColumn(bar_width=24, complete_style="green", finished_style="green"),
        *tail,
        TimeElapsedColumn(),
    ]


def _tag_fields() -> dict:
    return {"stamp": f"[{datetime.now():%H:%M:%S}]", "tag": "[ACTION]"}


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
        *_progress_columns([MofNCompleteColumn()]),
        console=_out,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=len(items), **_tag_fields())
        for item in items:
            yield item
            progress.advance(task)


def bytes_progress(description: str, total: int):
    """Context manager yielding an `advance(n_bytes)` callback under a size bar.

    tar.xz has no item count to iterate, so `track()` doesn't fit; this reports
    bytes read from the source tree instead.
    """
    from contextlib import contextmanager

    @contextmanager
    def _run():
        if not _out.is_terminal:
            yield lambda _n: None
            return
        with Progress(
            *_progress_columns([DownloadColumn()]),
            console=_out,
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=total, **_tag_fields())
            yield lambda n: progress.advance(task, n)

    return _run()


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
    # Same leading columns as a log line, so this doesn't jut out to the left.
    line = _tagged("INFO" if note else "ACTION", "")
    line.append(f"{current:>2}/{total} ", style="bold cyan")
    line.append("█" * done, style="green")
    line.append("░" * (width - done), style="bright_black")
    line.append(f" {title}", style="dim" if note else "bold")
    if note:
        line.append(f" ({note})", style="dim")
    # no_wrap: a long module name folding onto a second line breaks the column.
    _out.print(line, no_wrap=True, overflow="ellipsis")


def demo() -> None:
    banner("HTB Academy + TryHackMe -> Markdown")
    rule("289 Network Foundations", 2, 20)
    rule("34 Introduction to Networking", 3, 20, note="skipped")
    for line in ["→ Fetching module 90 metadata…", "  ✓ wrote 01-Intro.md",
                 "  • 15 section(s)", "     1. [theory     ] Overview",
                 "  auth error: HTTP 401", "Interrupted."]:
        say(line)
    assert _classify("→ x")[0] == "ACTION"   # → means "doing it now"
    assert _classify("  ✓ x")[0] == "SUCCESS"
    assert _classify("  ! x")[0] == "WARNING"
    assert _classify("  auth error: 401")[0] == "ERROR"
    # A glyph line loses its glyph; the [LEVEL] tag replaces it.
    assert _classify("  ✓ wrote a.md")[2] == "wrote a.md"
    # No glyph, no keyword: left alone so tables and prompts pass through.
    assert _classify("     1. [theory] Overview")[0] is None
    table(["#", "Type", "Title"],
          [[1, "theory", "Overview"], [2, "interactive", "Pre-Engagement"]],
          title="Sections")
    assert list(track([1, 2, 3], "demo")) == [1, 2, 3]
    with bytes_progress("demo", 10) as advance:
        advance(10)
    print("ui self-check passed")


if __name__ == "__main__":
    demo()
