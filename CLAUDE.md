# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `AGENTS.md` first** — it holds the detailed HTB rules (API layer
boundaries, converter conventions, image hosts, walkthroughs, cookie
auto-grab, the locked-content guard). This file covers what AGENTS.md doesn't:
the TryHackMe half and the shared pieces.

## What this is

Two scrapers over one shared toolkit, both writing Markdown for personal
offline study:

- **HTB Academy** — `htb_scraper.py` → `htb_api.py` + `converter.py`. One
  folder per module, one numbered `.md` per section, `assets/` for images.
- **TryHackMe** — `thm_scraper.py` → `thm_api.py`. One room → one `.md` file.

Shared: `cookiejar.py` (browser cookie grab for both) and `converter.py`
(`download_image`, `_split_code_and_text`, `_MD_IMG_RE`, `_collapse_blanks`
are reused by the THM scraper — don't duplicate them there).

## Commands

```bash
source .venv/bin/activate                     # PEP-668 Arch box; never pip install system-wide
pip install -r requirements.txt

python htb_scraper.py 293 --dry-run           # HTB: auth + section list, no files
python htb_scraper.py 293                     # HTB: full download
python thm_scraper.py csrfintroduction        # THM: room by slug (or full URL)
python thm_scraper.py <room> --dry-run

python test_thm.py                            # the only test suite; plain asserts, no pytest
python -m py_compile *.py                      # syntax check
```

See AGENTS.md for the rest of the HTB flags (`--debug-json`,
`--no-walkthrough`, `--reload-cookie`, …); THM takes the same
`--cookie/--cookie-file/--output/--timeout/--dry-run/--reload-cookie` set.

## THM specifics

- One endpoint: `GET /api/v2/rooms/tasks?roomCode=<slug>`. Referer must point
  at `/room/<slug>` (same requirement as HTB).
- Auth cookie is `connect.sid` (Express session), cached in **`cookies-thm.txt`**
  — separate file from HTB's `cookies.txt`. Both are gitignored secrets; never
  print cookie values.
- **THM descriptions are standard HTML**, unlike HTB's Markdown+HTML hybrid, so
  they go through bs4 + markdownify wholesale. Do *not* apply this approach to
  HTB (see AGENTS.md — it destroys HTB's Markdown structure).
- markdownify's `code_language_callback` gets the `<pre>`, but THM puts
  `class="language-x"` on the inner `<code>`; `html_to_markdown` copies the
  class up before converting. Keep that shim.
- Output is a single file with YAML frontmatter (`platform: thm`), `## Task N:`
  headings, and questions rendered with hints and the user's submitted answers.

## Testing

`test_thm.py` — plain `assert` functions, run as a script, no framework. Add
new checks there in the same style: synthetic HTML/dict input, one assert.
Anything end-to-end needs a real session cookie; use `--dry-run` to validate
auth before a full download.
