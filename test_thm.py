"""Self-check for the THM HTML→Markdown path. Run: python test_thm.py"""

import sys
from pathlib import Path

# The modules under test live in ./src/. Put that on the path so the imports
# below resolve when this file runs from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from thm_scraper import _format_question, build_room_md, html_to_markdown


def test_code_language_lifted_from_code_to_pre():
    md = html_to_markdown('<pre><code class="language-python">x = 1</code></pre>')
    assert "```python" in md, md


def test_images_in_code_fences_are_left_alone():
    from converter import _split_code_and_text
    chunks = _split_code_and_text("a\n```\n![x](y.png)\n```\nb")
    assert any(is_code and "![x](y.png)" in c for is_code, c in chunks), chunks


def test_question_renders_hint_and_answer():
    out = _format_question(
        {"question": "<p>What port?</p>", "hint": "<p>nmap</p>",
         "progress": {"submission": "80"}}, 1)
    assert "1. What port?" in out and "_Hint:_ nmap" in out, out
    assert "_Your answer:_ `80`" in out, out


def test_long_image_url_fits_filesystem_name_limit():
    """Mermaid diagrams embed the whole compressed diagram in the URL path."""
    from converter import _NAME_MAX_BYTES, _safe_filename
    url = "https://mermaid.ink/img/pako:" + "eNptkk1uwjAQha8y8rpc" * 30
    name = _safe_filename(url)
    assert len(name.encode("utf-8")) <= _NAME_MAX_BYTES, len(name)
    # Still unique per URL, and still an image.
    assert name != _safe_filename(url + "x"), name
    assert name.endswith(".png"), name


def test_room_md_has_frontmatter_and_tasks():
    md = build_room_md("demo", [{"taskNo": 1, "title": "Intro",
                                 "description": "<p>hi</p>", "questions": []}],
                       {"title": "Demo Room", "difficulty": "easy"})
    assert md.startswith("---\nplatform: thm\n"), md[:80]
    assert "## Task 1: Intro" in md and "hi" in md, md


def test_room_pipeline_real_shape_to_markdown():
    """End to end over the conversion pipeline: the (details, tasks) a source
    returns, straight through build_room_md, on a realistic THM shape."""
    details = {"title": "SQL Injection", "difficulty": "easy", "type": "walkthrough",
               "creators": [{"username": "tryhackme"}], "description": "Learn SQLi."}
    tasks = [
        {"taskNo": 1, "title": "Intro", "description": "<p>Welcome</p>", "questions": []},
        {"taskNo": 2, "title": "What is SQLi", "description": "<p>Body</p>",
         "questions": [{"question": "<p>Which port?</p>", "hint": "",
                        "progress": {"submission": "3306",
                                     "answerDescription": "Answer format: ****"}}]},
    ]
    md = build_room_md("sqli", tasks, details)
    assert 'title: "SQL Injection"' in md and 'difficulty: "easy"' in md, md[:120]
    assert "## Task 1: Intro" in md and "## Task 2: What is SQLi" in md, md
    assert "### Questions" in md and "1. Which port?" in md, md
    assert "_Your answer:_ `3306`" in md and "_Answer format:_ Answer format: ****" in md, md


def test_room_source_falls_back_to_browser_on_429():
    """fetch_room swaps API for the browser only when the API 429s (BotID)."""
    import sys as _sys
    import types
    import thm_api
    import thm_source

    class FakeClient:
        def __init__(self, **kw):
            pass

        def get_room_info(self):
            raise thm_api.THMAPIError("HTTP 429 Security Checkpoint")

        def get_room_tasks(self):
            return []

    fake_browser = types.ModuleType("thm_browser")
    fake_browser.fetch_room = lambda room, cookie, timeout=30: ({"title": "Browser"}, [{"taskNo": 1}])
    _sys.modules["thm_browser"] = fake_browser
    orig = thm_source.THMClient
    thm_source.THMClient = FakeClient
    try:
        details, tasks = thm_source.fetch_room("x", "connect.sid=y")
    finally:
        thm_source.THMClient = orig
        del _sys.modules["thm_browser"]
    assert details == {"title": "Browser"} and tasks == [{"taskNo": 1}], (details, tasks)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✓ {name}")
    print("all passed")
