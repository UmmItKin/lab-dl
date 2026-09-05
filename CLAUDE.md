# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It is the single source of truth for this repo. `AGENTS.md` only points here.

## What this is

Two scrapers over one shared toolkit, both writing Markdown for personal
offline study. HTB gives one folder per module (one numbered `.md` per section,
`assets/` for images, an optional "Show solution" walkthrough), and `htb path
<id>` does a whole job-role path. THM gives one `.md` per room. HTB content is
proprietary, so never upload, share, or redistribute what it exports.

```
main.py          # entry point: sys.path bootstrap, then hands off to cli.py
src/
  cli.py         # top-level parser: picks the platform, forwards the rest
  htb_scraper.py # HTB orchestration (argparse, run(), run_path())
  thm_scraper.py # THM orchestration
  htb_api.py     # HTBClient: endpoints, headers, {"data":…} unwrapping, auth errors
  thm_api.py     # THMClient: room details + tasks
  ui.py          # say(): sqlmap-style [time] [LEVEL] output, plus table/track/rule/banner
  converter.py   # content cleanup, HTML-fragment→Markdown, image download
  cookiejar.py   # read a session cookie from a Firefox-based browser profile
test_thm.py      # self-check; adds src/ to sys.path so it can import the modules
pyproject.toml   # deps, managed by uv; uv.lock pins them (both are committed)
cookies.txt      # USER SECRET, gitignored. Auto-written by the browser grab.
output/          # exported modules, gitignored
```

`main.py` and `test_thm.py` insert `src/` into `sys.path` at startup, so the
modules in `src/` keep bare imports (`from htb_api import …`). Do not rewrite
those to package-relative form. Python 3.9+.

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

- `htb_api.py` and `thm_api.py` are the only modules that talk to the network.
  They own endpoints, the mandatory `Referer` header, and unwrapping the
  `{"data": …}` envelope. Note the section list is v3 while everything else is
  v2.
- `converter.py` and `cookiejar.py` never import a scraper. `converter.py` is
  pure string in, string out, plus image downloads. Keep both cycle-free.
  `cookiejar.py` is imported lazily inside `_grab_and_cache`, so browser_cookie3
  stays an optional dependency.
- Both scrapers share `rewrite_images`, `slugify` and `json_quote` from
  `converter.py`. `rewrite_images` takes `resolve` and `referer` so THM points
  at its own host instead of copying the loop. Don't fork these again.
- A path run reuses `run()` per module rather than duplicating the section,
  walkthrough and image pipeline. Three non-obvious hooks make that work:
  `run_path` sets `args._module_dir` so modules nest under the path folder,
  `run()` reads that same attribute to know it should stay quiet (20 modules
  print 20 lines, not 20 tables), and it stashes its file count on
  `args._written` because the transient progress bar erases anything printed
  while it is live.
- `_confirm(q, assume_yes, default)` backs both path prompts, and the defaults
  are deliberately asymmetric: `-y` and a non-TTY stdin download but never
  compress. The archive is also skipped when any module failed, so a half path
  is never packed.
- A module with a README is treated as done and skipped unless `--force`, which
  is what makes an interrupted path run resumable. `run()` writes that README
  last, so a module killed midway is correctly redownloaded.

## Console output

- Everything goes through `ui.say()`, not `print()`. It renders sqlmap-style
  `[HH:MM:SS] [LEVEL] message`. The level comes from the line's leading glyph
  (`→` ACTION, `•` INFO, `✓` SUCCESS, `!` WARNING, `✗` ERROR), which `say()`
  strips because the tag replaces it. Call sites therefore pass plain strings
  and never a level, and those glyphs never reach the terminal. No emoji.
- A line with no glyph and no error keyword prints untouched. That is what
  keeps table bodies and progress bars unprefixed.
- Exactly one space follows the tag. Do not pad tags to a fixed width; aligning
  the bodies into a column reads like tab stops.
- Rich runs with `markup=False, highlight=False, soft_wrap=True`, because our
  output contains literal brackets (`[theory     ]`, `[!bash!]$`) that markup
  would eat and re-wrapping would break long paths. Pass a `rich.text.Text`
  with a style rather than inline `[bold]` tags.
- `ask()` writes its own escape codes because Rich's `print(end="")` did not
  reliably flush before `input()` blocks.
- `track`, `bytes_progress`, `rule` and `banner` fall back to plain output on a
  non-TTY. All of them start with the same timestamp and tag columns as a log
  line, so a live bar lines up with the messages around it. `rule` uses block
  glyphs deliberately unlike `track`'s `━`, so the outer path bar and the inner
  section bar can't be confused.

## HTB conversion rules

- HTB section bodies are Markdown with embedded HTML fragments, not pure HTML.
  Never pass the whole document through an HTML to Markdown engine (html2text
  and friends): it collapses Markdown newlines into spaces and destroys the
  structure. Convert only the fragments HTB emits, and only outside fenced code
  blocks (`_split_code_and_text`). This was a real bug, so don't reintroduce it.
- `_normalize_code_quirks` handles the payload's oddities: CRLF, the
  `-session` language suffixes, and `[!bash!]$` prompts.
- `_strip_redundant_h1` drops the body's leading `# <SectionTitle>` because
  `build_section_md` already emits the title as H1.
- Sections sort by the `page` field across groups, which matches the website,
  then re-number 1..N.
- Image URLs: `/content/…` goes to the CDN host, everything else relative goes
  to the academy host, and an academy-host 404 retries on the CDN. The filename
  carries a hash of the URL to avoid collisions and is truncated so a long URL
  can't exceed the filesystem's 255-byte limit.
- The walkthrough body is the `instructions` field, not `content` like
  sections. `walkthrough_id`'s location in the module response is not
  confirmed, so the code looks it up defensively and skips when absent. If a
  module has one but it doesn't appear, run `--debug-json` and fix the lookup.

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

- Cookie auto-grab (`cookiejar.py`): with no cookie file, or with
  `--reload-cookie`, the scraper scans every Firefox-based browser profile and
  reads the session from whichever one is actually logged in. Do NOT trust
  profiles.ini's `Default=1`; it often points at a profile the user isn't
  using. Firefox stores cookie values in plaintext, so this is a plain sqlite
  read. Chromium would need decryption and is out of scope.
- A cached cookie only reveals it's expired once the API rejects it, so on a
  401/403 at the first request both scrapers re-grab, re-cache, and retry once.
  That retry is skipped for `--cookie`, which has no browser source to re-grab
  from. Don't remove it.
- `load_cookie` deliberately skips `#` comments and non-ASCII text, because
  requests encodes headers as latin-1. Keep that guard.
- Locked-content guard: if `is_unlocked == false` and `progress == 0`, refuse
  to proceed. This avoids an accidental cube spend. Don't remove it.
- Cookie files and `output/` are gitignored. Never print or log a cookie value.

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
