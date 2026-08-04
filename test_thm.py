"""Self-check for the THM HTML→Markdown path. Run: python test_thm.py"""

from thm_scraper import _format_question, build_room_md, html_to_markdown


def test_code_language_lifted_from_code_to_pre():
    md = html_to_markdown('<pre><code class="language-python">x = 1</code></pre>')
    assert "```python" in md, md


def test_images_in_code_fences_are_left_alone():
    from thm_scraper import _split_code_and_text
    chunks = _split_code_and_text("a\n```\n![x](y.png)\n```\nb")
    assert any(is_code and "![x](y.png)" in c for is_code, c in chunks), chunks


def test_question_renders_hint_and_answer():
    out = _format_question(
        {"question": "<p>What port?</p>", "hint": "<p>nmap</p>",
         "progress": {"submission": "80"}}, 1)
    assert "1. What port?" in out and "_Hint:_ nmap" in out, out
    assert "_Your answer:_ `80`" in out, out


def test_room_md_has_frontmatter_and_tasks():
    md = build_room_md("demo", [{"taskNo": 1, "title": "Intro",
                                 "description": "<p>hi</p>", "questions": []}],
                       {"title": "Demo Room", "difficulty": "easy"})
    assert md.startswith("---\nplatform: thm\n"), md[:80]
    assert "## Task 1: Intro" in md and "hi" in md, md


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✓ {name}")
    print("all passed")
