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
converter.py     # content cleanup + HTML-fragment→Markdown + image download (CDN fallback)
requirements.txt # requests (stdlib-only otherwise; html2text was removed — do not re-add)
cookies.txt      # USER SECRET — gitignored. Raw Cookie: header. See cookies.txt.example.
output/          # exported modules — gitignored
```

## Commands

```bash
source .venv/bin/activate                 # PEP-668 Arch env; never pip install system-wide
pip install -r requirements.txt
python htb_scraper.py 293 --dry-run       # auth + section list, writes no files (first check)
python htb_scraper.py 293                 # full download
python htb_scraper.py 23 --debug-json     # dump raw API JSON to find field names (e.g. walkthrough_id)
python htb_scraper.py 23 --no-walkthrough # sections only, skip the "Show solution" walkthrough
python htb_scraper.py <id|url> --cookie "..." --output ./notes
python -m py_compile htb_api.py converter.py htb_scraper.py   # syntax check
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
- **`htb_scraper.py` orchestrates**: loads cookie → fetches metadata → checks
  the locked-content guard → per section: convert, rewrite images, write file →
  (optional) fetch walkthrough, convert, write as `NN-Walkthrough.md` → write
  module README.

## Critical conventions

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

## Security / secrets

- `cookies.txt`, `output/`, `.venv/` are gitignored. **Never print or log the
  cookie value** — when debugging, log only length/prefix-truncated.
- The cookie loader (`load_cookie`) intentionally skips `#` comment lines and
  non-ASCII text (requests encodes headers as latin-1). Keep that guard.
- Locked-content guard: if `is_unlocked == false` and `progress == 0`, refuse to
  proceed (avoids an accidental cube spend). Don't remove it.

## Testing without a live cookie

The converter and pure helpers can be unit-tested with synthetic HTB-style
strings (see the heredoc tests used during development). End-to-end runs need
the user's real session cookie — `--dry-run` first to validate auth before a
full download.
