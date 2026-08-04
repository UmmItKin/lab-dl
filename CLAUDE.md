# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` first. It holds the detailed HTB rules: API layer boundaries,
converter conventions, image hosts, walkthroughs, cookie auto-grab, and the
locked-content guard. This file covers what AGENTS.md doesn't, which is the
TryHackMe half and the pieces both scrapers share.

## What this is

Two scrapers over one shared toolkit, both writing Markdown for personal
offline study:

- HTB Academy: `htb_scraper.py` on top of `htb_api.py` and `converter.py`. One
  folder per module, one numbered `.md` per section, `assets/` for images.
- TryHackMe: `thm_scraper.py` on top of `thm_api.py`. One room becomes one
  `.md` file.

Three modules are shared. `ui.py` provides `say()`, a colored drop-in for
`print()`, plus `table()` for listings; output uses the glyphs `→ ✓ ✗ • !` and
no emoji. `cookiejar.py` does the browser cookie grab for both platforms.
`converter.py` exports `download_image`, `_split_code_and_text`, `_MD_IMG_RE`,
and `_collapse_blanks`, which the THM scraper reuses, so don't reimplement them
there.

## Commands

Dependencies live in `pyproject.toml`, pinned by the committed `uv.lock`. Add
one with `uv add <pkg>`. Never hand-edit the lock, and note there is no
`requirements.txt` any more.

```bash
uv sync                                              # PEP-668 Arch box; never pip install system-wide

uv run python htb_scraper.py 293 --dry-run           # HTB: auth + section list, no files
uv run python htb_scraper.py 293                     # HTB: full download
uv run python thm_scraper.py csrfintroduction        # THM: room by slug (or full URL)
uv run python thm_scraper.py <room> --dry-run

uv run python ui.py                                  # color self-check
uv run python test_thm.py                            # the only test suite; plain asserts, no pytest
uv run python -m py_compile *.py                     # syntax check
```

AGENTS.md lists the rest of the HTB flags (`--debug-json`, `--no-walkthrough`,
`--reload-cookie`, and so on). THM takes the same
`--cookie/--cookie-file/--output/--timeout/--dry-run/--reload-cookie` set.

## THM specifics

- One endpoint: `GET /api/v2/rooms/tasks?roomCode=<slug>`. Referer must point
  at `/room/<slug>`, the same requirement HTB has.
- The auth cookie is `connect.sid`, an Express session, cached in
  `cookies-thm.txt`. That is a separate file from HTB's `cookies.txt`. Both are
  gitignored secrets, so never print cookie values.
- THM descriptions are standard HTML, unlike HTB's Markdown and HTML hybrid, so
  they go through bs4 and markdownify wholesale. Do not apply that approach to
  HTB; as AGENTS.md explains, it destroys HTB's Markdown structure.
- markdownify's `code_language_callback` gets the `<pre>`, but THM puts
  `class="language-x"` on the inner `<code>`, so `html_to_markdown` copies the
  class up before converting. Keep that shim.
- Output is a single file with YAML frontmatter (`platform: thm`), `## Task N:`
  headings, and questions rendered with hints and the user's submitted answers.

## Testing

`test_thm.py` is plain `assert` functions run as a script, with no framework.
Add new checks there in the same style: synthetic HTML or dict input, one
assert. Anything end to end needs a real session cookie, so use `--dry-run` to
validate auth before a full download.
