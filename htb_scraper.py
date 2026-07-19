#!/usr/bin/env python3
"""Download a HackTheBox Academy module as structured Markdown.

Usage:
    python htb_scraper.py 293
    python htb_scraper.py https://academy.hackthebox.com/module/293
    python htb_scraper.py 293 --cookie "htb_academy_session=...; XSRF-TOKEN=..."
    python htb_scraper.py 293 --cookie-file ~/htb-cookies.txt --output ./notes
    python htb_scraper.py 293 --dry-run     # metadata + section list, no files

Cookies are read from (in priority order):
    --cookie "..."        inline
    --cookie-file PATH    a file containing the raw Cookie header on one line
    ./cookies.txt         default (gitignored)

This tool is for personal study only. Do not redistribute HTB Academy content.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

from htb_api import HTBAuthError, HTBClient, HTBNotFoundError, HTBAPIError
from converter import content_to_markdown, rewrite_images


# ---------------------------------------------------------------------------
# Argument / cookie helpers
# ---------------------------------------------------------------------------

_MODULE_URL_RE = re.compile(
    r"academy\.hackthebox\.com/(?:app/)?module/(\d+)(?:/section/(\d+))?"
)


def parse_target(arg: str) -> tuple[int, int | None]:
    """Accept a bare module id, a module URL, or a section URL. Returns
    (module_id, optional_section_id)."""
    arg = arg.strip()
    if arg.isdigit():
        return int(arg), None
    m = _MODULE_URL_RE.search(arg)
    if not m:
        raise ValueError(
            f"Could not parse a module id from: {arg!r}. "
            "Pass a numeric id or an academy.hackthebox.com/module/<id> URL."
        )
    module_id = int(m.group(1))
    section_id = int(m.group(2)) if m.group(2) else None
    return module_id, section_id


def load_cookie(args: argparse.Namespace) -> str:
    """Resolve the cookie header string from CLI flags or cookies.txt."""
    if args.cookie:
        return args.cookie.strip()

    cookie_file = Path(args.cookie_file) if args.cookie_file else Path("cookies.txt")
    if not cookie_file.exists():
        raise SystemExit(
            f"Cookie file not found: {cookie_file}\n"
            "Either pass --cookie '...' / --cookie-file PATH, or create "
            "./cookies.txt (see cookies.txt.example)."
        )
    raw = cookie_file.read_text(encoding="utf-8")

    # The cookie value must be ASCII-safe (requests encodes headers as latin-1),
    # so anything non-ASCII is either a comment or stray text — never part of a
    # real session cookie. Filter to cookie-shaped fragments only.
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # A cookie line is name=value pairs joined by ';'. If the non-comment
        # line still contains spaces outside values, it's prose — skip it.
        if "=" not in line:
            continue
        parts.append(line)
    cookie = "; ".join(p.rstrip(";") for p in parts)

    if not cookie:
        raise SystemExit(
            f"{cookie_file} has no cookie data (only comments/blank lines). "
            "Paste your htb_academy_session cookie on its own line."
        )
    if "PASTE_VALUE_HERE" in cookie:
        raise SystemExit(
            f"{cookie_file} still has the placeholder value. "
            "Edit it and paste your real htb_academy_session cookie."
        )
    if "htb_academy_session=" not in cookie:
        raise SystemExit(
            f"{cookie_file} doesn't contain 'htb_academy_session='. "
            "Make sure you copied that cookie from DevTools."
        )
    try:
        cookie.encode("latin-1")
    except UnicodeEncodeError:
        # Last-resort guard: strip any remaining non-ASCII so the request can't
        # blow up with a codec error.
        cookie = cookie.encode("ascii", "ignore").decode("ascii")
    return cookie


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip()
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def _section_filename(num: int, title: str) -> str:
    return f"{num:02d}-{_slugify(title)}.md"


def _module_dir_name(module_id: int, name: str) -> str:
    return f"{module_id:03d}-{_slugify(name)}"


# ---------------------------------------------------------------------------
# README (module-level) generation
# ---------------------------------------------------------------------------

def _first_string(value) -> str:
    """HTB's takeaways sometimes come as str, sometimes as {'content': ...} or
    {'title': ...}. Normalize to a plain string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in ("content", "title", "name", "text"):
            if k in value and isinstance(value[k], str):
                return value[k].strip()
    return ""


def build_readme(module_id: int, info: dict, sections: list[dict]) -> str:
    name = info.get("name", f"Module {module_id}")
    difficulty = (info.get("difficulty") or {}).get("title", "—")
    tier = (info.get("tier") or {}).get("name", "—")
    category = (info.get("category") or {}).get("title", "—")
    est = info.get("estimated_time_of_completion", "—")
    author = (info.get("author") or {}).get("name", "—")

    lines = [
        f"# {name}",
        "",
        f"- **Module ID:** {module_id}",
        f"- **Category:** {category}",
        f"- **Difficulty:** {difficulty}",
        f"- **Tier:** {tier}",
        f"- **Estimated time:** {est}",
        f"- **Author:** {author}",
        f"- **Sections:** {len(sections)}",
        "",
    ]

    description = info.get("description")
    if description:
        lines += ["## Description", "", description.strip(), ""]

    prelude = info.get("prelude")
    if prelude:
        lines += ["## Module Summary", "", prelude.strip(), ""]

    lines += ["## Sections", ""]
    for s in sections:
        fname = _section_filename(s["num"], s["title"])
        type_tag = f" _({s.get('type', '')})_" if s.get("type") else ""
        lines.append(f"{s['num']}. [{s['title']}]({fname}){type_tag}")
    lines.append("")

    takeaways = info.get("takeaways") or []
    takeaways = [_first_string(t) for t in takeaways]
    takeaways = [t for t in takeaways if t]
    if takeaways:
        lines += ["## Key Takeaways", ""]
        lines += [f"- {t}" for t in takeaways]
        lines.append("")

    conclusion = info.get("conclusion")
    if conclusion:
        lines += ["## Conclusion", "", conclusion.strip(), ""]

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Section file generation
# ---------------------------------------------------------------------------

def _format_questions(questions: list[dict]) -> str:
    if not questions:
        return ""
    out = ["", "## Questions", ""]
    for q in questions:
        order = q.get("order") or ""
        text = q.get("question", "").strip()
        hint = (q.get("hint") or "").strip()
        prefix = f"{order}. " if order else "- "
        out.append(f"{prefix}{text}")
        if hint:
            out.append(f"  - _Hint:_ {hint}")
    out.append("")
    return "\n".join(out)


def build_section_md(
    section: dict,
    module_id: int,
    info: dict,
    content_md: str,
    questions_md: str,
) -> str:
    frontmatter = [
        "---",
        f"module: {json_quote(info.get('name', ''))}",
        f"module_id: {module_id}",
        f"section: {json_quote(section.get('title', ''))}",
        f"section_id: {section['id']}",
        f"section_num: {section['num']}/{len(info.get('_section_count', '?'))}",
        f"type: {json_quote(section.get('type', ''))}",
        f"group: {json_quote(section.get('group', ''))}",
        f"url: https://academy.hackthebox.com/app/module/{module_id}/section/{section['id']}",
        "---",
        "",
        f"# {section.get('title', f'Section {section['num']}')}",
        "",
    ]
    return "\n".join(frontmatter) + content_md + questions_md


def json_quote(s: str) -> str:
    """YAML-safe quoting for frontmatter values."""
    s = "" if s is None else str(s)
    if s == "":
        return '""'
    if re.match(r"^[\w\s.,:/-]+$", s):
        return f'"{s}"'
    return '"' + s.replace('"', '\\"') + '"'


def _strip_redundant_h1(md: str, title: str) -> str:
    """If the converted content starts with '# <title>' (which HTB bodies do),
    drop that first H1 — build_section_md already emits the title as an H1, so
    keeping both produces a doubled heading."""
    if not md or not title:
        return md
    lines = md.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == f"# {title.strip()}":
            del lines[i]
            # Also swallow a single blank line left right after it.
            if i < len(lines) and lines[i].strip() == "":
                del lines[i]
        break  # only inspect the first non-empty line
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    cookie = load_cookie(args)
    module_id, only_section_id = parse_target(args.target)

    client = HTBClient(cookie=cookie, timeout=args.timeout)
    client.set_referer(module_id)

    print(f"→ Fetching module {module_id} metadata…")
    try:
        info = client.get_module(module_id)
    except HTBAuthError as e:
        print(f"  auth error: {e}", file=sys.stderr)
        return 2
    except HTBNotFoundError as e:
        print(f"  not found: {e}", file=sys.stderr)
        return 3

    name = info.get("name", f"Module {module_id}")
    print(f"  • {name}")

    # Locked-content guard: don't accidentally spend cubes.
    is_unlocked = info.get("is_unlocked", True)
    progress = info.get("progress", 0)
    if is_unlocked is False and (progress or 0) == 0:
        print(
            "  ⚠ This module is locked (is_unlocked=false, progress=0).\n"
            "    Unlock it in the HTB Academy UI first, then re-run.\n"
            "    (Refusing to proceed to avoid an unintended cube spend.)",
            file=sys.stderr,
        )
        return 4

    print(f"→ Fetching section list…")
    sections = client.get_sections(module_id)
    info["_section_count"] = [None] * len(sections)  # for frontmatter num/total
    if not sections:
        print("  ! No sections returned. The module may be empty or the API changed.",
              file=sys.stderr)
        return 5

    if only_section_id is not None:
        sections = [s for s in sections if s["id"] == only_section_id]
        if not sections:
            print(f"  ! Section {only_section_id} not found in module {module_id}.",
                  file=sys.stderr)
            return 6

    print(f"  • {len(sections)} section(s)")
    for s in sections:
        print(f"      {s['num']:>2}. [{s.get('type',''):<11}] {s['title']}")

    if args.dry_run:
        print("\n--dry-run: not writing any files. ✅")
        return 0

    # Output directory.
    out_root = Path(args.output)
    module_dir = out_root / _module_dir_name(module_id, name)
    assets_dir = module_dir / "assets"
    module_dir.mkdir(parents=True, exist_ok=True)

    http = requests.Session()
    written: list[Path] = []

    for s in sections:
        print(f"\n→ Section {s['num']}/{len(sections)}: {s['title']}")
        client.set_referer(module_id)
        try:
            data = client.get_section_content(module_id, s["id"])
        except (HTBAPIError, requests.RequestException) as e:
            print(f"  ! failed to fetch section content: {e}", file=sys.stderr)
            continue

        raw = (data or {}).get("content", "") or ""
        questions = (data or {}).get("questions", []) or []
        md = content_to_markdown(raw)
        md = rewrite_images(md, assets_dir, http, cookie, quiet=args.quiet)
        # HTB section bodies begin with "# <SectionTitle>" — same title we emit
        # in build_section_md. Strip the redundant leading H1 so output isn't
        # doubled (matches what you'd see rendered on the website).
        md = _strip_redundant_h1(md, s.get("title", ""))
        questions_md = _format_questions(questions)
        section_md = build_section_md(s, module_id, info, md, questions_md)

        fname = _section_filename(s["num"], s["title"])
        dest = module_dir / fname
        dest.write_text(section_md, encoding="utf-8")
        written.append(dest)
        print(f"  ✓ wrote {dest.relative_to(out_root)}")

        if not args.no_jitter:
            time.sleep(1.5)

    # Module-level README with TOC.
    readme = build_readme(module_id, info, sections)
    readme_path = module_dir / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    written.append(readme_path)

    print(f"\n✅ Done. {len(written)} file(s) under {module_dir.relative_to(out_root)}/")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="htb_scraper.py",
        description=(
            "Download a HackTheBox Academy module as structured Markdown. "
            "For personal study only — do not redistribute HTB content."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python htb_scraper.py 293\n"
            '  python htb_scraper.py 293 --cookie "htb_academy_session=..."\n'
            "  python htb_scraper.py 293 --dry-run\n"
            "  python htb_scraper.py https://academy.hackthebox.com/module/293\n"
        ),
    )
    p.add_argument(
        "target",
        help="Module id (e.g. 293) or full module/section URL.",
    )
    p.add_argument(
        "--cookie", default=None,
        help='Raw Cookie header string, e.g. "htb_academy_session=...; XSRF-TOKEN=...".',
    )
    p.add_argument(
        "--cookie-file", default=None,
        help="Path to a file containing the Cookie header (default: ./cookies.txt).",
    )
    p.add_argument(
        "--output", default="output",
        help="Output directory (default: ./output).",
    )
    p.add_argument(
        "--timeout", type=int, default=30,
        help="Per-request HTTP timeout in seconds (default: 30).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Fetch module metadata + section list only; write no files.",
    )
    p.add_argument(
        "--no-jitter", action="store_true",
        help="Disable the 1.5s sleep between sections (faster, less polite).",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Less verbose output.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except (HTBAuthError, HTBNotFoundError, HTBAPIError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
