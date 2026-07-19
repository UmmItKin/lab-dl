# HTB-Module

Download a [HackTheBox Academy](https://academy.hackthebox.com) module as
structured Markdown for personal offline study — **one folder per module, one
numbered `.md` file per section, images saved locally.**

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

## ⚠️ Disclaimer

This tool is for **personal study only**. HackTheBox Academy content is
proprietary. Do not upload, share, or redistribute anything you download with
this tool. You must have legitimate access to (have unlocked) any module you
export. The contributors of this tool are not responsible for misuse.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.9+ (uses `from __future__ import annotations`).

## Get your cookie

Programmatic login is blocked by reCAPTCHA / 2FA, so we reuse your logged-in
session cookie — the same approach used by other open-source HTB tools.

1. Log into <https://academy.hackthebox.com> in your browser.
2. Open DevTools (**F12**) → **Application** (or **Storage**) → **Cookies** →
   `https://academy.hackthebox.com`.
3. Copy the value of the **`htb_academy_session`** cookie. The `XSRF-TOKEN`
   cookie is useful too.
4. Build a `Cookie:` header:
   `htb_academy_session=eyJpdiI6...; XSRF-TOKEN=eyJpdiI6...`
5. Put it in `cookies.txt` (copy `cookies.txt.example`) **or** pass it with
   `--cookie "..."`.

`cookies.txt` is gitignored — it will never be committed.

## Usage

```bash
# By module id (reads ./cookies.txt by default)
python htb_scraper.py 293

# By URL (module or section)
python htb_scraper.py https://academy.hackthebox.com/module/293
python htb_scraper.py https://academy.hackthebox.com/module/293/section/1234

# Inline cookie
python htb_scraper.py 293 --cookie "htb_academy_session=...; XSRF-TOKEN=..."

# Custom output dir
python htb_scraper.py 293 --output ./notes

# Dry run — auth check + section list, no files written
python htb_scraper.py 293 --dry-run
```

### Flags

| Flag | Purpose |
| --- | --- |
| `--cookie "..."` | Inline `Cookie:` header string. |
| `--cookie-file PATH` | File containing the cookie header (default `./cookies.txt`). |
| `--output DIR` | Output directory (default `./output`). |
| `--timeout N` | Per-request HTTP timeout in seconds (default `30`). |
| `--dry-run` | Fetch metadata + section list only; write nothing. |
| `--no-jitter` | Disable the inter-section sleep (faster, less polite). |
| `--quiet` | Less verbose output. |

### Looping over many modules

```bash
for id in 293 112 15; do
  python htb_scraper.py "$id"
done
```

## How it works

Hits the same JSON API the Academy web app uses (all `GET`, cookie-auth):

| Purpose | Endpoint |
| --- | --- |
| Module metadata | `/api/v2/modules/{id}` |
| Section list | `/api/v3/modules/{id}/sections` |
| Section content | `/api/v2/modules/{id}/sections/{sid}` |

Each request carries your `Cookie:` header plus `Accept: application/json` and a
`Referer` pointing at the module page. Responses are `{"data": ...}`; the client
unwraps them. Sections are ordered by their `page` field to match the website.

Section bodies are a **Markdown + embedded-HTML** hybrid with HTB-specific
quirks (`\r\n` line endings, `[!bash!]$` prompts, `-session` language suffixes,
`<div class="alert">` callouts). `converter.py` normalizes all of that and
converts the embedded HTML fragments (alerts, cards, `<img>`, inline
`<strong>`/`<em>`/`<code>`/`<a>`, lists, headings) to Markdown — but only
outside fenced code blocks, and without running the whole document through an
HTML engine (which would collapse the existing Markdown's newlines). Images are
downloaded locally, falling back to HTB's CDN host when the main host 404s an
asset.

### Locked content

If a module reports `is_unlocked == false` and `progress == 0`, the tool refuses
to proceed — to avoid an accidental cube spend. Unlock it in the Academy UI
first, then re-run.

## Project layout

```
htb_scraper.py    CLI entry + orchestration
htb_api.py        HTBClient: endpoints, headers, JSON unwrapping, auth errors
converter.py      content cleanup, HTML→Markdown, image download
requirements.txt  requests
cookies.txt.example
.gitignore        excludes cookies.txt, output/, venv/
```

## Troubleshooting

- **`HTB rejected the request (HTTP 401/403)` / `returned HTML instead of JSON`** —
  your cookie is missing or expired. Re-copy `htb_academy_session` from your
  browser. Session cookies expire; refresh them and retry.
- **404 on a section** — you may only have partial access to the module.
- **Images missing** — some assets only resolve via the CDN; the downloader
  tries that fallback automatically. Re-run if a few fail.
