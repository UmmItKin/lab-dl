<div align="center">

# lab-dl

Download HackTheBox Academy modules and TryHackMe rooms as clean Markdown,
for personal offline study.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=for-the-badge&logo=uv&logoColor=white)
![HTB Academy](https://img.shields.io/badge/HTB-Academy-9FEF00?style=for-the-badge&logo=hackthebox&logoColor=black)
![TryHackMe](https://img.shields.io/badge/TryHackMe-rooms-212C42?style=for-the-badge&logo=tryhackme&logoColor=white)

![updated](https://img.shields.io/github/last-commit/UmmItKin/lab-dl?style=for-the-badge&logo=git&logoColor=white&label=updated&color=111418)

</div>

---

## Install

```bash
uv sync
```

## Use

```bash
uv run python htb_scraper.py 293                 # HTB module by id or URL
uv run python thm_scraper.py csrfintroduction    # THM room by slug or URL
uv run python htb_scraper.py 293 --dry-run       # check auth, write nothing
```

No cookie setup needed if you are logged in to either site in a Firefox-based
browser (Floorp, Firefox, LibreWolf, Zen, Waterfox). The scraper reads the
session from your profile and caches it to `cookies.txt` / `cookies-thm.txt`,
both gitignored. If a cached cookie expires it is re-grabbed automatically.

To pass one by hand instead: `--cookie "htb_academy_session=..."` or put it in
`cookies.txt` (see `cookies.txt.example`).

## Output

```
output/
  293-Introduction-to-Information-Security/
    README.md              # module metadata + contents
    01-Introduction.md
    02-InfoSec-Domains.md
    assets/                # images, downloaded locally
  csrfintroduction.md      # THM rooms are one file each
```

HTB pages are a Markdown and HTML hybrid, so `converter.py` handles the
embedded fragments (alerts, cards, images, inline tags) without letting an HTML
engine flatten the surrounding Markdown. THM pages are plain HTML and go
through markdownify. Images are rewritten to local paths in both.

## Flags

| Flag | Purpose |
| --- | --- |
| `--cookie "..."` | Inline `Cookie:` header. |
| `--cookie-file PATH` | Read the header from a file. |
| `--reload-cookie` | Force a fresh grab from the browser. |
| `--output DIR` | Output directory (default `./output`). |
| `--timeout N` | HTTP timeout in seconds (default `30`). |
| `--dry-run` | List sections or tasks, write nothing. |

HTB only: `--debug-json` dumps the raw API response, `--no-walkthrough` skips
the "Show solution" file, `--no-jitter` drops the polite inter-section sleep,
`--quiet` trims the output.

## Notes

- If a module is locked (`is_unlocked == false`, `progress == 0`) the tool
  refuses to run, so you cannot spend a cube by accident. Unlock it in the
  Academy UI first.
- A few images only resolve on HTB's CDN. The downloader retries there
  automatically; re-run if any fail.
- `AGENTS.md` documents the API layout and conventions in detail.

## Disclaimer

For personal study only. HTB Academy and TryHackMe content is proprietary.
Export only what you have legitimate access to, and do not upload, share, or
redistribute it. The contributors are not responsible for misuse.
