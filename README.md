# HTB-Module

Download a [HackTheBox Academy](https://academy.hackthebox.com) module as
structured Markdown for personal offline study: one folder per module, one
numbered `.md` file per section, images saved locally.

```
output/
  293-Introduction-to-Information-Security/
    README.md              # module metadata + table of contents
    01-Introduction.md
    02-InfoSec-Domains.md
    03-Threats.md
    ...
    assets/
      <images>.png
```

## Disclaimer

This tool is for personal study only. HackTheBox Academy content is
proprietary. Do not upload, share, or redistribute anything you download with
it, and only export modules you have legitimate access to (that is, ones you
have unlocked). The contributors of this tool are not responsible for misuse.

## Install

This project uses [uv](https://docs.astral.sh/uv/). It creates the venv and
installs the locked dependencies for you:

```bash
uv sync
```

Then prefix commands with `uv run`, as below, or activate the venv it made with
`source .venv/bin/activate` and drop the prefix.

Requires Python 3.9+ (it uses `from __future__ import annotations`).

## Get your cookie

Programmatic login is blocked by reCAPTCHA and 2FA, so we reuse your logged-in
session cookie, the same approach other open-source HTB tools take.

### Option A: auto-grab from your browser (easiest)

If you use a Firefox-based browser (Floorp, Firefox, LibreWolf, Zen, or
Waterfox) and you're already logged in to HTB Academy, just run the scraper
with no cookie at all. It will find the session in your browser profile:

```bash
uv run python htb_scraper.py 293        # auto-grabs cookie on first run
```

The grabbed cookie is cached to `cookies.txt`, so later runs are instant. To
force a refresh, for example after the session expires:

```bash
uv run python htb_scraper.py 293 --reload-cookie
```

This needs the `browser_cookie3` dependency, which `uv sync` installs.

### Option B: manual

1. Log into <https://academy.hackthebox.com> in your browser.
2. Open DevTools (**F12**), then **Application** (or **Storage**), then
   **Cookies**, then `https://academy.hackthebox.com`.
3. Copy the value of the `htb_academy_session` cookie. The `XSRF-TOKEN` cookie
   is useful too.
4. Build a `Cookie:` header:
   `htb_academy_session=eyJpdiI6...; XSRF-TOKEN=eyJpdiI6...`
5. Put it in `cookies.txt` (copy `cookies.txt.example`), or pass it with
   `--cookie "..."`.

`cookies.txt` is gitignored, so it will never be committed.

## Usage

```bash
# By module id (reads ./cookies.txt by default)
uv run python htb_scraper.py 293

# By URL (module or section)
uv run python htb_scraper.py https://academy.hackthebox.com/module/293
uv run python htb_scraper.py https://academy.hackthebox.com/module/293/section/1234

# Inline cookie
uv run python htb_scraper.py 293 --cookie "htb_academy_session=...; XSRF-TOKEN=..."

# Custom output dir
uv run python htb_scraper.py 293 --output ./notes

# Dry run: auth check + section list, no files written
uv run python htb_scraper.py 293 --dry-run

# Re-grab cookie from browser (after session expires)
uv run python htb_scraper.py 293 --reload-cookie
```

### Flags

| Flag | Purpose |
| --- | --- |
| `--cookie "..."` | Inline `Cookie:` header string. |
| `--cookie-file PATH` | File containing the cookie header (default `./cookies.txt`). |
| `--reload-cookie` | Re-grab the cookie from your browser, overwriting `cookies.txt`. |
| `--output DIR` | Output directory (default `./output`). |
| `--timeout N` | Per-request HTTP timeout in seconds (default `30`). |
| `--dry-run` | Fetch metadata and the section list only; write nothing. |
| `--debug-json` | Dump raw module and section JSON to stdout, for inspecting API fields. |
| `--no-walkthrough` | Skip downloading the module's "Show solution" walkthrough. |
| `--no-jitter` | Disable the inter-section sleep (faster, less polite). |
| `--quiet` | Less verbose output. |

### Looping over many modules

```bash
for id in 293 112 15; do
  uv run python htb_scraper.py "$id"
done
```

## How it works

The tool hits the same JSON API the Academy web app uses. All calls are `GET`
and authenticated by cookie:

| Purpose | Endpoint |
| --- | --- |
| Module metadata | `/api/v2/modules/{id}` |
| Section list | `/api/v3/modules/{id}/sections` |
| Section content | `/api/v2/modules/{id}/sections/{sid}` |

Each request carries your `Cookie:` header plus `Accept: application/json` and a
`Referer` pointing at the module page. Responses are wrapped as `{"data": ...}`
and the client unwraps them. Sections are ordered by their `page` field to match
the website.

Section bodies are a hybrid of Markdown and embedded HTML, with HTB-specific
quirks: `\r\n` line endings, `[!bash!]$` prompts, `-session` language suffixes,
and `<div class="alert">` callouts. `converter.py` normalizes all of that and
converts the embedded HTML fragments (alerts, cards, `<img>`, inline `<strong>`,
`<em>`, `<code>`, `<a>`, lists, and headings) to Markdown. It does so only
outside fenced code blocks, and without running the whole document through an
HTML engine, which would collapse the existing Markdown's newlines. Images are
downloaded locally, falling back to HTB's CDN host when the main host 404s an
asset.

### Locked content

If a module reports `is_unlocked == false` and `progress == 0`, the tool refuses
to proceed, to avoid an accidental cube spend. Unlock it in the Academy UI
first, then re-run.

## Project layout

```
htb_scraper.py    CLI entry + orchestration
htb_api.py        HTBClient: endpoints, headers, JSON unwrapping, auth errors
converter.py      content cleanup, HTML→Markdown, image download
ui.py             colored console output (say/table)
pyproject.toml    dependencies (managed by uv; uv.lock pins them)
cookies.txt.example
.gitignore        excludes cookies.txt, output/, venv/
```

## Troubleshooting

- `HTB rejected the request (HTTP 401/403)` or `returned HTML instead of JSON`:
  your cookie is missing or expired. Sessions do expire; the scraper will now
  re-grab from your browser automatically, or you can pass `--reload-cookie`.
- 404 on a section: you may only have partial access to the module.
- Missing images: some assets only resolve via the CDN, and the downloader tries
  that fallback automatically. Re-run if a few fail.
