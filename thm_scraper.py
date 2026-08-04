"""TryHackMe room downloader.

Fetches a room's task list from the THM API and writes it as a single
Markdown file (one room → one .md). Task descriptions are HTML and are
converted to Markdown via markdownify; images are downloaded locally.

Run it directly:
    python thm_scraper.py csrfintroduction
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

import cookiejar
from converter import (
    _collapse_blanks,
    _MD_IMG_RE,
    _split_code_and_text,
    download_image,
)
from thm_api import THM_BASE, THMAPIError, THMAuthError, THMClient, THMNotFoundError


# ---------------------------------------------------------------------------
# HTML → Markdown
# ---------------------------------------------------------------------------

def html_to_markdown(html: str) -> str:
    """Convert THM task description HTML to clean Markdown.

    THM descriptions are clean, standard HTML (<p>, <h1-6>, <ul>, <ol>, <pre>,
    <code>, <img>, <a>, <strong>, <em>). markdownify (BeautifulSoup-based) does
    the heavy lifting. One THM-specific fix is needed: THM puts
    `class="language-xxx"` on the inner <code>, but markdownify's
    code_language_callback receives the <pre> element (upstream bug), so we
    copy the language class onto the <pre> before converting.
    """
    if not html or not html.strip():
        return ""

    from bs4 import BeautifulSoup
    from markdownify import MarkdownConverter

    # Pre-process: lift language-xxx class from <code> onto its parent <pre>.
    soup = BeautifulSoup(html, "html.parser")
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        if not code:
            continue
        code_classes = code.get("class", []) or []
        if isinstance(code_classes, str):
            code_classes = code_classes.split()
        lang_classes = [c for c in code_classes if c.startswith("language-")]
        if lang_classes:
            pre_classes = pre.get("class", []) or []
            if isinstance(pre_classes, str):
                pre_classes = pre_classes.split()
            # Avoid duplicating if already present.
            for lc in lang_classes:
                if lc not in pre_classes:
                    pre_classes.append(lc)
            pre["class"] = pre_classes

    def _code_language(el):
        classes = el.get("class", []) or []
        if isinstance(classes, str):
            classes = classes.split()
        for cls in classes:
            if cls.startswith("language-"):
                return cls[len("language-"):]
        return None

    md_text = MarkdownConverter(
        heading_style="ATX",
        bullets="-",
        code_language_callback=_code_language,
        strip=["script", "iframe", "style"],  # drop embedded JS/CSS/trackers
    ).convert(str(soup))

    return _collapse_blanks(md_text).strip() + "\n"


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def rewrite_images(
    md: str, assets_dir: Path, session: requests.Session, cookie: str
) -> str:
    """Download every Markdown image and rewrite the link to a local path.
    Skips fenced code blocks so `![...]()` inside a snippet stays literal."""
    def repl(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2).strip()
        url = urljoin(THM_BASE, src)  # THM srcs are usually absolute already
        local = download_image(
            url, assets_dir, session, cookie, referer=THM_BASE + "/"
        )
        if local is None:
            return f"![{alt}]({url})"  # keep remote on failure
        rel = Path("assets") / local.name
        return f"![{alt}]({rel.as_posix()})"

    return "\n".join(
        chunk if is_code else _MD_IMG_RE.sub(repl, chunk)
        for is_code, chunk in _split_code_and_text(md)
    )


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    s = s.strip("-")
    return s[:60] or "untitled"


def _yaml_quote(s: str) -> str:
    return json.dumps("" if s is None else str(s), ensure_ascii=False)


def _format_question(q: dict, q_idx: int) -> str:
    """One question → markdown block. Includes the question text (HTML→MD),
    any hint, and (if the user already answered it) their submission."""
    qtext_html = q.get("question", "") or ""
    qtext = html_to_markdown(qtext_html).strip()
    lines: list[str] = [f"{q_idx}. {qtext}"]
    hint = (q.get("hint") or "").strip()
    if hint:
        hint_md = html_to_markdown(hint).strip()
        lines.append(f"   - _Hint:_ {hint_md}")
    prog = q.get("progress") or {}
    no_answer = prog.get("noAnswer", False)
    if no_answer:
        lines.append("   - _(no answer needed)_")
    else:
        submission = (prog.get("submission") or "").strip()
        if submission:
            lines.append(f"   - _Your answer:_ `{submission}`")
        ans_fmt = (prog.get("answerDescription") or "").strip()
        if ans_fmt and ans_fmt != "No answer needed":
            lines.append(f"   - _Answer format:_ {ans_fmt}")
    return "\n".join(lines)


def build_room_md(room_code: str, tasks: list[dict], room_meta: dict | None = None) -> str:
    """Assemble the full room markdown: frontmatter + title + per-task sections."""
    meta = room_meta or {}
    title = meta.get("title") or room_code
    description = meta.get("description", "")
    difficulty = meta.get("difficulty", "")
    room_type = meta.get("type", "")
    creators = [c.get("username", "") for c in (meta.get("creators") or [])]
    creators_str = ", ".join(c for c in creators if c)

    frontmatter = [
        "---",
        "platform: thm",
        f"room: {_yaml_quote(room_code)}",
        f"title: {_yaml_quote(title)}",
        f"difficulty: {_yaml_quote(difficulty)}",
        f"type: {_yaml_quote(room_type)}",
        f"creators: {_yaml_quote(creators_str)}",
        f"url: https://tryhackme.com/room/{room_code}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if description:
        frontmatter.append(f"> {description.strip()}")
        frontmatter.append("")

    body: list[str] = []
    for task in sorted(tasks, key=lambda t: t.get("taskNo", 0)):
        task_no = task.get("taskNo", "?")
        task_title = task.get("title", f"Task {task_no}")
        desc_html = task.get("description", "") or ""
        desc_md = html_to_markdown(desc_html).strip()
        questions = task.get("questions", []) or []

        body.append(f"## Task {task_no}: {task_title}")
        body.append("")
        if desc_md:
            body.append(desc_md)
            body.append("")
        if questions:
            body.append("### Questions")
            body.append("")
            for i, q in enumerate(questions, 1):
                body.append(_format_question(q, i))
                body.append("")

    return "\n".join(frontmatter) + "\n" + "\n".join(body).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    # Cookie: same priority as HTB scraper (--cookie > file > browser grab).
    if args.cookie:
        cookie = args.cookie.strip()
    else:
        cookie_file = Path(args.cookie_file) if args.cookie_file else Path("cookies-thm.txt")
        if getattr(args, "reload_cookie", False) or not cookie_file.exists():
            if not cookie_file.exists():
                print(f"→ No {cookie_file} found. Auto-grabbing from your browser…")
            cookie = cookiejar.grab_thm_cookie()
            cookiejar.save_to_cookie_file(cookie, cookie_file)
            print(f"  ✓ saved to {cookie_file}")
        else:
            raw = cookie_file.read_text(encoding="utf-8").strip()
            if not raw or "connect.sid=" not in raw:
                print(f"→ {cookie_file} has no connect.sid; re-grabbing from browser…")
                cookie = cookiejar.grab_thm_cookie()
                cookiejar.save_to_cookie_file(cookie, cookie_file)
            else:
                cookie = raw

    room_code = args.room.strip()
    # Accept full URL: https://tryhackme.com/room/<code>
    m = re.search(r"tryhackme\.com/(?:room|r/room)/([^/?#]+)", room_code)
    if m:
        room_code = m.group(1)

    client = THMClient(cookie=cookie, room_code=room_code, timeout=args.timeout)

    print(f"→ Fetching room {room_code!r}…")
    try:
        room_info = client.get_room_info(room_code)
        tasks = client.get_room_tasks(room_code)
    except THMAuthError as e:
        print(f"  auth error: {e}", file=sys.stderr)
        return 2
    except THMNotFoundError as e:
        print(f"  not found: {e}", file=sys.stderr)
        return 3
    except THMAPIError as e:
        print(f"  API error: {e}", file=sys.stderr)
        return 1

    title = room_info.get("title", room_code)
    print(f"  • {title} — {len(tasks)} task(s)")
    for t in sorted(tasks, key=lambda t: t.get("taskNo", 0)):
        qcount = len(t.get("questions", []) or [])
        print(f"      Task {t.get('taskNo')}: {t.get('title')} ({qcount} Q)")

    if args.dry_run:
        print("\n--dry-run: not writing any files. ✅")
        return 0

    # Output: one .md per room.
    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)
    assets_dir = out_root / "assets"
    out_file = out_root / f"{_slugify(room_code)}.md"

    http = requests.Session()

    # Download + convert.
    md = build_room_md(room_code, tasks, room_info)
    md = rewrite_images(md, assets_dir, http, cookie)

    out_file.write_text(md, encoding="utf-8")
    print(f"\n✅ Wrote {out_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="thm_scraper.py",
        description="Download a TryHackMe room as Markdown. Personal study only.",
    )
    p.add_argument("room", help="Room code (e.g. csrfintroduction) or full room URL.")
    p.add_argument("--cookie", default=None, help="Raw Cookie header for tryhackme.com.")
    p.add_argument("--cookie-file", default=None, help="File containing the cookie (default: ./cookies-thm.txt).")
    p.add_argument("--output", default="output", help="Output directory (default: ./output).")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout (default: 30).")
    p.add_argument("--dry-run", action="store_true", help="List tasks only; write nothing.")
    p.add_argument("--reload-cookie", action="store_true", help="Re-grab cookie from browser.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
