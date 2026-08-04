# AGENTS.md

Guidance for ZCode agents working in this repo.

## What this is

A Python CLI that downloads a single HackTheBox Academy module (using the
user's session cookie) and saves it as structured Markdown: **one folder per
module, one numbered `.md` per section, plus an optional walkthrough ("Show
solution") file, images downloaded locally.**

For personal study only — HTB content is proprietary. Never upload, share, or
redistribute exported content.

## Layout

```
htb_scraper.py   # CLI entry + orchestration (argparse, run()). Run this directly.
htb_api.py       # HTBClient: the 4 API endpoints, headers, {"data":…} unwrapping, auth errors
ui.py            # say() + table(): colored console output (rich); color picked from the line's leading glyph
converter.py     # content cleanup + HTML-fragment→Markdown + image download (CDN fallback)
cookiejar.py     # auto-grab htb_academy_session from a local Firefox-based browser profile
pyproject.toml   # deps, managed by uv; uv.lock pins them (both are committed)
cookies.txt      # USER SECRET — gitignored. Raw Cookie: header. Auto-written by the browser grab.
output/          # exported modules — gitignored
```

## Commands

```bash
uv sync                                          # PEP-668 Arch env; never pip install system-wide
uv run python htb_scraper.py 293 --dry-run       # auth + section list, writes no files (first check)
uv run python htb_scraper.py 293                 # full download (auto-grabs cookie if no cookies.txt)
uv run python htb_scraper.py 293 --reload-cookie # re-grab cookie from browser, overwrite cookies.txt
uv run python htb_scraper.py 23 --debug-json     # dump raw API JSON to find field names (e.g. walkthrough_id)
uv run python htb_scraper.py 23 --no-walkthrough # sections only, skip the "Show solution" walkthrough
uv run python htb_scraper.py <id|url> --cookie "..." --output ./notes
uv run python -m py_compile htb_api.py converter.py cookiejar.py htb_scraper.py   # syntax check
```

Python 3.9+ (`from __future__ import annotations` is used).

## Architecture / layer rules

- **`htb_api.py` is the only module that talks to the network for content.** It
  owns endpoints, the mandatory `Referer: …/app/module/{id}` header, `Accept:
  application/json`, and unwrapping `payload.get("data", payload)`. Endpoints
  (all GET): `/api/v2/modules/{id}`, `/api/v3/modules/{id}/sections` (note v3),
  `/api/v2/modules/{id}/sections/{sid}`, `/api/v2/walkthroughs/{wid}`.
- **`converter.py` never imports `htb_scraper`.** It's pure: string in → string
  out, plus image downloads (which take a `requests.Session` + cookie arg). Keep
  it import-cycle-free.
- **`cookiejar.py` never imports `htb_scraper`.** It only reads the browser's
  cookies.sqlite (via browser_cookie3) and returns a cookie header string. It's
  imported lazily inside `_grab_and_cache` so the browser_cookie3 dependency is
  optional — `--cookie`/cookies.txt still work without it.
- **`htb_scraper.py` orchestrates**: loads cookie (file, flag, or browser grab)
  → fetches metadata → checks the locked-content guard → per section: convert,
  rewrite images, write file → (optional) fetch walkthrough, convert, write as
  `NN-Walkthrough.md` → write module README.

## Critical conventions

- **Console output goes through `ui.say()`, not `print()`.** It's a
  print-compatible wrapper over Rich that derives the color from the line's
  leading glyph (`→` cyan, `✓` green, `•` white, error lines red), so message
  strings stay plain text and call sites pass no styles. Rich is deliberately
  configured `markup=False, highlight=False, soft_wrap=True`: our output
  contains literal brackets (`[theory     ]`, `[!bash!]$`) that Rich markup
  would eat, and re-wrapping would break long paths. `say(..., file=sys.stderr)`
  routes to the stderr console. `ui.table(columns, rows, title=…)` renders list
  output (section/task listings). **No emoji in output** — only the plain
  glyphs `→ ✓ ✗ • !`.

- **HTB section bodies are Markdown with *embedded HTML fragments*, NOT pure
  HTML.** Never pass the whole document through an HTML→Markdown engine
  (html2text, etc.) — it collapses Markdown newlines into spaces and destroys
  structure. Convert *only* the specific fragments HTB emits (`<div class="alert
  …">`, `<div class="card [bg-light…]"><div class="card-body">`, `<img>`, inline
  `<strong>/<em>/<code>/<a>`, `<ul>/<li>`, headings), and **only outside fenced
  code blocks** (use `_split_code_and_text`). This was a real bug — don't
  reintroduce it.
- **HTB-specific cleanups** (in `_normalize_code_quirks`): `\r\n`→`\n`;
  `shell-session`→`shell`, `powershell-session`→`powershell`, `cmd-session`→`shell`;
  strip `[!bash!]$` prompts (both ` [!bash!]$ ` and `[!bash!]$ ` forms).
- **Duplicate H1**: HTB bodies start with `# <SectionTitle>`. `_strip_redundant_h1`
  removes it because `build_section_md` already emits the title as H1.
- **Section ordering**: sort by the `page` field across groups (matches the
  website), then re-number 1..N.
- **Image URLs**: `/content/…` → CDN host `https://cdn.services-k8s.prod.aws.htb.systems`;
  everything else relative → academy host. On academy-host 404, retry on CDN.
  Hash the URL into the filename to avoid basename collisions. Walkthrough images
  use `/storage/walkthroughs/{wid}/…` paths — these fall through to the academy
  host (no `/content/` prefix), which is correct.
- **Walkthrough ("Show solution")**: the skill-assessment walkthrough lives at
  `GET /api/v2/walkthroughs/{walkthrough_id}` and the Markdown body is the
  `instructions` field of the response (NOT `content` like sections). It's pure
  Markdown + `\r\n` (no alert/card HTML fragments), so it reuses the same
  `content_to_markdown` + `rewrite_images` pipeline. Output is one standalone
  `NN-Walkthrough.md` numbered after the last section. The `walkthrough_id`
  source field on the module response is **not confirmed** — the code looks it
  up defensively (`info.get("walkthrough_id")`) and silently skips if absent.
  If a module has a walkthrough but the field name differs, run `--debug-json`
  to inspect the raw module response and fix the lookup.
- **Cookie auto-grab** (`cookiejar.py`): when no `cookies.txt` exists (or
  `--reload-cookie` is passed), the scraper scans every Firefox-based browser
  profile (`~/.floorp`, `~/.mozilla/firefox`, `~/.librewolf`, `~/.zen`,
  `~/.waterfox` + macOS/Windows equivalents) and reads `htb_academy_session`
  from whichever profile is actually logged in. **Do NOT trust profiles.ini's
  `Default=1`** — it often points at a profile the user isn't actively using;
  scan all profiles and pick the one holding the cookie. Firefox-based browsers
  store cookie values in plaintext (no key4.db decryption needed); Chromium
  support would require decryption and is intentionally out of scope. The
  grabbed cookie is cached to `cookies.txt` so subsequent runs skip the scan.
  `browser_cookie3` is imported lazily so the feature degrades gracefully if
  the package isn't installed.

## Security / secrets

- `cookies.txt`, `output/`, `.venv/` are gitignored. **Never print or log the
  cookie value** — when debugging, log only length/prefix-truncated.
- The cookie loader (`load_cookie`) intentionally skips `#` comment lines and
  non-ASCII text (requests encodes headers as latin-1). Keep that guard.
- The browser auto-grab reads cookies directly from the user's own browser
  profile on their own machine — it never transmits cookies anywhere except to
  `academy.hackthebox.com` (the site they're already logged in to). The grabbed
  value is written to the gitignored `cookies.txt`.
- Locked-content guard: if `is_unlocked == false` and `progress == 0`, refuse to
  proceed (avoids an accidental cube spend). Don't remove it.

## Testing without a live cookie

The converter and pure helpers can be unit-tested with synthetic HTB-style
strings (see the heredoc tests used during development). End-to-end runs need
the user's real session cookie — `--dry-run` first to validate auth before a
full download.
