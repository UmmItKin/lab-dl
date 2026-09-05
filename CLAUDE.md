# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It is the single source of truth for this repo. `AGENTS.md` only points here.

## What this is

Two scrapers over one shared toolkit, both writing Markdown for personal
offline study:

- HTB Academy: `htb_scraper.py` on top of `htb_api.py` and `converter.py`. One
  folder per module, one numbered `.md` per section, `assets/` for images, and
  an optional walkthrough ("Show solution") file. `htb path <id>` downloads a
  whole job-role path.
- TryHackMe: `thm_scraper.py` on top of `thm_api.py`. One room becomes one
  `.md` file.

HTB content is proprietary, so never upload, share, or redistribute what it
exports.

## Layout

```
main.py          # entry point: sys.path bootstrap, then hands off to cli.py
src/
  cli.py         # top-level parser: picks the platform, forwards the rest
  htb_scraper.py # HTB orchestration (argparse, run(), run_path())
  thm_scraper.py # THM orchestration
  htb_api.py     # HTBClient: the 5 endpoints, headers, {"data":…} unwrapping, auth errors
  thm_api.py     # THMClient: room details + tasks
  ui.py          # say(): sqlmap-style [time] [LEVEL] output, plus table/track/rule/banner
  converter.py   # content cleanup + HTML-fragment→Markdown + image download (CDN fallback)
  cookiejar.py   # auto-grab cookies from a local Firefox-based browser profile
test_thm.py      # self-check; adds src/ to sys.path so it can import the modules
pyproject.toml   # deps, managed by uv; uv.lock pins them (both are committed)
cookies.txt      # USER SECRET, gitignored. Raw Cookie: header. Auto-written by the browser grab.
output/          # exported modules, gitignored
```

`main.py` and `test_thm.py` insert `src/` into `sys.path` at startup. The
modules in `src/` keep bare imports (`from htb_api import …`); do not rewrite
those to package-relative form.

Python 3.9+ (`from __future__ import annotations` is used).

## Commands

Dependencies live in `pyproject.toml`, pinned by the committed `uv.lock`. Add
one with `uv add <pkg>`. Never hand-edit the lock, and note there is no
`requirements.txt` any more.

```bash
uv sync                                              # PEP-668 Arch box; never pip install system-wide

uv run python main.py htb 293 --dry-run              # HTB: auth + section list, no files
uv run python main.py htb 293                        # HTB: full download
uv run python main.py htb path 419                   # HTB: whole path; prompts to download, then to tar.xz
uv run python main.py htb 293 --reload-cookie        # re-grab the cookie, overwrite cookies.txt
uv run python main.py htb 23 --debug-json            # dump raw API JSON to find field names
uv run python main.py htb 23 --no-walkthrough        # sections only
uv run python main.py thm csrfintroduction           # THM: room by slug (or full URL)

uv run python main.py htb --help                     # that scraper's real flags
uv run python src/ui.py                              # color self-check
uv run python src/cli.py                             # dispatch self-check
uv run python test_thm.py                            # the only test suite; plain asserts, no pytest
uv run python -m py_compile src/*.py main.py         # syntax check
```

`main.py` only claims `-h/--help` before a platform is named. After that the
scraper's own parser owns it, so the flag list can never drift from the code.

## Architecture and layer rules

- `htb_api.py` is the only module that talks to the network for HTB content. It
  owns endpoints, the mandatory `Referer` header, `Accept: application/json`,
  and unwrapping `payload.get("data", payload)`. Endpoints (all GET):
  `/api/v2/modules/{id}`, `/api/v3/modules/{id}/sections` (note v3),
  `/api/v2/modules/{id}/sections/{sid}`, `/api/v2/walkthroughs/{wid}`,
  `/api/v2/paths/{id}`.
- `converter.py` never imports either scraper. It's pure: string in, string
  out, plus image downloads, which take a `requests.Session` and a cookie arg.
  Keep it import-cycle-free. Both scrapers share `rewrite_images`, `slugify`
  and `json_quote` from here; `rewrite_images` takes `resolve` and `referer`
  arguments so THM points at its own host instead of copying the loop.
- `cookiejar.py` never imports either scraper. It only reads the browser's
  cookies.sqlite (via browser_cookie3) and returns a cookie header string. It's
  imported lazily inside `_grab_and_cache` so the browser_cookie3 dependency
  stays optional; `--cookie` and cookies.txt still work without it.
- `htb_scraper.py` orchestrates. It loads the cookie (file, flag, or browser
  grab), fetches metadata, checks the locked-content guard, then per section
  converts, rewrites images, and writes the file. Afterwards it optionally
  fetches the walkthrough, converts it, writes it as `NN-Walkthrough.md`, and
  finally writes the module README.
- Paths: `htb path <id>` calls `GET /api/v2/paths/{id}`, whose `modules` list is
  the curriculum in order. `run_path()` loops it and reuses `run()` per module
  by copying args and setting `_module_dir`, so the section, walkthrough and
  image pipeline is not duplicated. Modules land in
  `NNN-Path/NN-<id>-Module/`. `run()` checks `_module_dir` to tell a path run
  from a solo one and suppresses its per-module table and chatter, so 20
  modules print 20 lines, not 20 tables. The transient progress bar erases
  anything printed while it is live, so the file count is stashed on
  `args._written` and printed by `run_path` afterwards.
- A module with a README is skipped unless `--force`, so an interrupted path
  run resumes. One failure doesn't abort the rest. The run prompts `[y/N]`
  before writing and again at the end to offer a `.tar.xz`.
  `_confirm(q, assume_yes, default)` backs both: `-y` and a non-TTY stdin fall
  through to `default`, which is True for the download and False for the
  archive, so an unattended run downloads but never compresses. The archive is
  skipped when any module failed, so a half path is never packed.

## Console output

- Everything goes through `ui.say()`, not `print()`. It renders sqlmap-style
  `[HH:MM:SS] [LEVEL] message` lines. The level comes from the line's leading
  glyph (`→` ACTION, `•` INFO, `✓` SUCCESS, `!` WARNING, `✗` ERROR), which
  `say()` strips because the tag replaces it, so message strings stay plain
  text and no call site passes a level. A line with no glyph and no error
  keyword prints untouched, which keeps table bodies and progress bars
  unprefixed.
- Exactly one space follows the tag. Do not pad tags to a fixed width; aligning
  the bodies into a column reads like tab stops.
- No emoji anywhere. The glyphs `→ ✓ ✗ • !` appear only in source at call
  sites, as the marker `say()` reads and strips, so they never reach the
  terminal.
- The rest of `ui.py`: `table(columns, rows, title=…)` for listings and prints
  its title as a tagged `[INFO]` line rather than using Rich's own title;
  `track(items, desc)` wraps a long loop in one live progress bar instead of a
  line per item; `bytes_progress(desc, total)` does the same for work with no
  item count, which is what the tar.xz step uses; `rule(title, i, n)` prints one
  compact `i/n ███░░░ title` header per module in a path run, using block glyphs
  deliberately unlike `track()`'s `━` so the outer and inner bars don't look
  alike; `banner()` prints the wordmark once from `main.py`. Both bars start
  with the same `[HH:MM:SS] [ACTION]` columns as a log line (see
  `_progress_columns`), so a live bar lines up with the messages around it.
- `ask()` prints an `[INPUT]` prompt. It writes the escape codes itself because
  Rich's `print(end="")` did not reliably flush before `input()` blocks, and
  `_confirm` in the scraper goes through it so prompts match the log lines.
- `track`, `rule` and `banner` fall back to plain output when stdout isn't a
  TTY. Rich is deliberately configured `markup=False, highlight=False,
  soft_wrap=True`: our output contains literal brackets (`[theory     ]`,
  `[!bash!]$`) that Rich markup would eat, and re-wrapping would break long
  paths. Because `markup=False`, pass a `rich.text.Text` with a style rather
  than inline `[bold]` tags. `say(..., file=sys.stderr)` routes to the stderr
  console.

## HTB conversion rules

- HTB section bodies are Markdown with embedded HTML fragments, not pure HTML.
  Never pass the whole document through an HTML to Markdown engine (html2text
  and friends), because it collapses Markdown newlines into spaces and destroys
  structure. Convert only the specific fragments HTB emits (`<div class="alert
  …">`, `<div class="card [bg-light…]"><div class="card-body">`, `<img>`, inline
  `<strong>/<em>/<code>/<a>`, `<ul>/<li>`, headings), and only outside fenced
  code blocks (use `_split_code_and_text`). This was a real bug, so don't
  reintroduce it.
- HTB-specific cleanups (in `_normalize_code_quirks`): `\r\n` to `\n`;
  `shell-session` to `shell`, `powershell-session` to `powershell`,
  `cmd-session` to `shell`; strip `[!bash!]$` prompts (both the ` [!bash!]$ `
  and `[!bash!]$ ` forms).
- Duplicate H1: HTB bodies start with `# <SectionTitle>`. `_strip_redundant_h1`
  removes it because `build_section_md` already emits the title as H1.
- Section ordering: sort by the `page` field across groups, which matches the
  website, then re-number 1..N.
- Image URLs: `/content/…` goes to the CDN host
  `https://cdn.services-k8s.prod.aws.htb.systems`; everything else relative goes
  to the academy host. On an academy-host 404, retry on the CDN. Hash the URL
  into the filename to avoid basename collisions, and truncate the stem so a
  long URL can't exceed the filesystem's 255-byte limit. Walkthrough images use
  `/storage/walkthroughs/{wid}/…` paths, which fall through to the academy host
  because they have no `/content/` prefix. That is correct.
- Walkthrough ("Show solution"): it lives at
  `GET /api/v2/walkthroughs/{walkthrough_id}` and the Markdown body is the
  `instructions` field of the response, not `content` like sections. It's pure
  Markdown with `\r\n` and no alert or card HTML fragments, so it reuses the
  same `content_to_markdown` and `rewrite_images` pipeline. Output is one
  standalone `NN-Walkthrough.md` numbered after the last section. The
  `walkthrough_id` source field on the module response is not confirmed, so the
  code looks it up defensively (`info.get("walkthrough_id")`) and silently skips
  if it's absent. If a module has a walkthrough but the field name differs, run
  `--debug-json` to inspect the raw module response and fix the lookup.

## THM specifics

- Two endpoints, both taking `roomCode`: `/api/v2/rooms/details` and
  `/api/v2/rooms/tasks`. Referer must point at `/room/<slug>`, the same
  requirement HTB has. `THMClient` is bound to one room, so the room code comes
  from the constructor rather than each call.
- The auth cookie is `connect.sid`, an Express session, cached in
  `cookies-thm.txt`. That is a separate file from HTB's `cookies.txt`. Both are
  gitignored secrets, so never print cookie values.
- THM descriptions are standard HTML, unlike HTB's Markdown and HTML hybrid, so
  they go through bs4 and markdownify wholesale. Do not apply that approach to
  HTB; see the conversion rules above for why it destroys HTB's structure.
- markdownify's `code_language_callback` gets the `<pre>`, but THM puts
  `class="language-x"` on the inner `<code>`, so `html_to_markdown` copies the
  class up before converting. Keep that shim.
- Output is a single file with YAML frontmatter (`platform: thm`), `## Task N:`
  headings, and questions rendered with hints and the user's submitted answers.

## Cookies and secrets

- Cookie auto-grab (`cookiejar.py`): when no cookie file exists, or when
  `--reload-cookie` is passed, the scraper scans every Firefox-based browser
  profile (`~/.floorp`, `~/.mozilla/firefox`, `~/.librewolf`, `~/.zen`,
  `~/.waterfox`, plus the macOS and Windows equivalents) and reads the session
  from whichever profile is actually logged in. Do NOT trust profiles.ini's
  `Default=1`; it often points at a profile the user isn't actively using, so
  scan all profiles and pick the one holding the cookie. Firefox-based browsers
  store cookie values in plaintext, so no key4.db decryption is needed.
  Chromium support would require decryption and is intentionally out of scope.
- A cached cookie only reveals it's expired once the API rejects it, so on an
  HTTP 401/403 at the first request both scrapers re-grab from the browser,
  re-cache, and retry once. That retry is skipped when the cookie came from
  `--cookie`, since a hand-supplied value has no browser source. Don't remove it.
- `cookies.txt`, `cookies-thm.txt`, `output/` and `.venv/` are gitignored. Never
  print or log a cookie value; when debugging, log only its length or a
  truncated prefix.
- The cookie loader (`load_cookie`) intentionally skips `#` comment lines and
  non-ASCII text, because requests encodes headers as latin-1. Keep that guard.
- The browser auto-grab reads cookies from the user's own profile on their own
  machine. It never transmits them anywhere except to the site they're already
  logged in to.
- Locked-content guard: if `is_unlocked == false` and `progress == 0`, refuse to
  proceed. This avoids an accidental cube spend. Don't remove it.

## Testing

`test_thm.py` is plain `assert` functions run as a script, with no framework.
Its `__main__` auto-discovers every `test_*` function, so running the file
runs the whole suite; there is no per-test flag. To exercise one check in
isolation, call it directly:

```bash
uv run python -c "import test_thm; test_thm.test_code_language_lifted_from_code_to_pre()"
```

Add new checks there in the same style: synthetic HTML or dict input, one
assert. `src/ui.py` and `src/cli.py` carry their own `demo()` self-checks, run
by executing the file. Anything end to end needs a real session cookie, so use
`--dry-run` to validate auth before a full download.

## Commits

Auto-commit only documentation: `CLAUDE.md`, `AGENTS.md`, and `/init` output.
For code changes (`*.py`, `pyproject.toml`, `uv.lock`, `README.md`, config),
show the diff and let the user review before committing. Commit messages are
one line: a Conventional Commits prefix (`feat:`, `fix:`, `docs:`, …) and a
short subject, no body.

## Comments

Keep code comments light. A module gets a one-line docstring saying what it is,
not a multi-paragraph essay on how it works. Skip the inline comment that just
restates the line below it; write comments only where the reason isn't obvious
from the code (a non-obvious workaround, an API quirk, a deliberate corner cut).
Match the density of the file you're editing, and don't add a new "一大段" block
where a short line does.

## Writing style

All English prose in this repo (docs, READMEs, chat replies, user-facing
strings) follows the `/humanizer:humanizer` style by default, not only when
that command is invoked. No em or en dashes, no emoji, active voice with real
subjects rather than passive or subjectless fragments, and none of the common
AI tells (rule-of-three padding, boldface used as emphasis, words like "delve",
"leverage", "vibrant"). Run `/humanizer:humanizer` on any substantial new prose
to catch the rest.
