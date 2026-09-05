# AGENTS.md

lab-dl downloads HackTheBox Academy modules and TryHackMe rooms as Markdown.
Library code lives in `src/`, run through `main.py`:

```bash
uv sync
uv run python main.py htb 293 --dry-run   # safest first command
uv run python test_thm.py                 # the test suite
```

[CLAUDE.md](CLAUDE.md) is the single source of truth. Read it before
changing anything. It covers the layout, the layer rules, the console output
conventions, the HTB and THM scraping quirks, cookie handling, and the commit
and writing-style rules. Do not duplicate any of that here; this file is a
pointer so tools looking for `AGENTS.md` land in the right place.
