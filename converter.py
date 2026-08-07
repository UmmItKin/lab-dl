"""Convert HTB Academy section content to clean Markdown, and download images.

HTB section bodies are a hybrid: mostly Markdown with embedded HTML fragments
(<img>, <div class="alert ...">, <div class="card">, inline <code>/<strong>/<a>,
etc.). The raw payload also uses CRLF line endings and HTB-specific code-block
quirks (`[!bash!]$` prompts, `-session` language suffixes).

The strategy:
  1. Normalize line endings + HTB-specific code quirks first.
  2. Convert the embedded HTML fragments to Markdown, but ONLY outside fenced
     code blocks (so example HTML shown inside ``` fences is preserved verbatim).
  3. Clean up whitespace.

Images are downloaded into an assets/ folder next to the .md file and the
Markdown links are rewritten to point at the local copy. Image hosts:
  - `/content/...` paths live on the CDN host.
  - everything else relative lives on the academy host.
If the academy host 404s an image, we retry the same path on the CDN host
(HTB sometimes only serves certain assets from the CDN).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from htb_api import CDN_BASE, HTB_BASE, USER_AGENT


# ---------------------------------------------------------------------------
# 1. Content cleanup
# ---------------------------------------------------------------------------

# Regex object so the loop below is a bit faster.
_FENCE_RE = re.compile(r"^\s*```")


def _normalize_code_quirks(md: str) -> str:
    """Fix HTB-specific code-block markers (applied once, globally — these
    strings never appear legitimately outside code contexts)."""
    md = md.replace("shell-session", "shell")
    md = md.replace("powershell-session", "powershell")
    md = md.replace("cmd-session", "shell")
    # HTB prompt prefix, with/without a leading space.
    md = md.replace(" [!bash!]$ ", " ")
    md = md.replace("[!bash!]$ ", "")
    md = md.replace("[!bash!]", "")
    return md


def _deindent_fences(md: str) -> str:
    """Strip leading whitespace from lines that are just ``` fences, so deeply
    indented blocks render as real code blocks in Markdown."""
    out = []
    for line in md.split("\n"):
        if _FENCE_RE.match(line):
            out.append(line.lstrip())
        else:
            out.append(line)
    return "\n".join(out)


def _collapse_blanks(md: str) -> str:
    """Collapse 3+ blank lines to 2, and drop a `---` immediately after a heading."""
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"(^#{1,6}\s.*\n)\s*---\s*\n", r"\1", md, flags=re.MULTILINE)
    return md


def _split_code_and_text(md: str):
    """Yield (is_code, chunk) tuples by splitting on ``` fences. Used so we can
    run HTML→Markdown transforms only on the non-code parts."""
    parts = []
    in_code = False
    current = []
    for line in md.split("\n"):
        if _FENCE_RE.match(line):
            parts.append((in_code, "\n".join(current)))
            current = [line]
            in_code = not in_code
        else:
            current.append(line)
    parts.append((in_code, "\n".join(current)))
    return parts


# --- per-tag HTML -> Markdown ---------------------------------------------
#
# HTB section bodies are Markdown with *embedded HTML fragments* — NOT pure
# HTML. Passing the whole document through an HTML→md engine (html2text)
# destroys the structure: HTML collapses newlines into spaces, mangling the
# Markdown that was already valid. So we do the opposite — walk the text and
# convert only the specific HTML fragments HTB emits, leaving everything else
# (existing markdown) untouched. Newlines are preserved throughout.

import html as _html  # stdlib, for entity decoding

# <div class="alert alert-warning"> ... </div>  (also alert-danger, alert-info)
_ALERT_BLOCK_RE = re.compile(
    r'<div\s+class="alert\s+([^"<>]*?)">([\s\S]*?)</div>', re.IGNORECASE
)
# Generic card container: <div class="card [bg-light|...]"><div class="card-body">...</div></div>
# HTB cards often carry extra modifier classes (bg-light, border-*, text-*), so
# match "card" as one of several whitespace-separated classes.
_CARD_RE = re.compile(
    r'<div\s+class="[^"]*\bcard\b[^"]*">\s*'
    r'<div\s+class="[^"]*\bcard-body\b[^"]*">([\s\S]*?)</div>\s*</div>',
    re.IGNORECASE,
)
_IMG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE)
_IMG_ATTR_RE = re.compile(
    r'(src|alt|title)\s*=\s*"([^"]*)"', re.IGNORECASE
)
_TAG_RE = re.compile(
    r"</?(strong|b|em|i|code|p|br|hr|a|ul|ol|li|h[1-6]|blockquote)\b[^>]*>",
    re.IGNORECASE,
)
_LINK_RE = re.compile(
    r'<a\s+[^>]*?href\s*=\s*"([^"]*)"[^>]*>([\s\S]*?)</a>', re.IGNORECASE
)


def _convert_alerts(text: str) -> str:
    """Turn HTB callout boxes into Markdown blockquotes."""
    def repl(m: re.Match) -> str:
        cls = m.group(1).lower()
        body = m.group(2).strip()
        body = _convert_inline_html(body)
        label = "Warning" if any(k in cls for k in ("warning", "danger")) else "Note"
        # Multi-line body -> prefix every line with "> ".
        lines = [ln for ln in body.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return f"\n\n> **{label}:**\n\n"
        first, rest = lines[0], lines[1:]
        out = [f"> **{label}:** {first}".rstrip()]
        for ln in rest:
            out.append(f"> {ln}".rstrip() if ln.strip() else ">")
        return f"\n\n" + "\n".join(out) + f"\n\n"
    return _ALERT_BLOCK_RE.sub(repl, text)


def _convert_cards(text: str) -> str:
    def repl(m: re.Match) -> str:
        body = m.group(1).strip()
        body = _convert_inline_html(body)
        # Prefix every line of the body with "> " so it forms a real Markdown
        # blockquote (HTB cards are often multi-line with leading blanks).
        lines = [ln for ln in body.split("\n")]
        # Drop a single leading blank so the quote doesn't start with "> ".
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        quoted = "\n".join(f"> {ln}".rstrip() if ln.strip() else ">" for ln in lines)
        return f"\n\n{quoted}\n\n"
    return _CARD_RE.sub(repl, text)


def _convert_img_tag(tag: str) -> str:
    attrs = {k.lower(): v for k, v in _IMG_ATTR_RE.findall(tag)}
    src = attrs.get("src", "").strip()
    alt = attrs.get("alt", "").strip()
    if not src:
        return ""
    return f"![{alt}]({src})"


def _convert_links(text: str) -> str:
    """Convert <a href="...">label</a> -> [label](href). Labels may themselves
    contain <code>/<strong> etc., so recurse on the label first."""
    def repl(m: re.Match) -> str:
        href = m.group(1).strip()
        label = _convert_inline_html(m.group(2)).strip()
        if not href:
            return label
        return f"[{label}]({href})"
    return _LINK_RE.sub(repl, text)


def _convert_simple_tags(text: str) -> str:
    """Convert the remaining inline/block tags HTB uses."""
    out = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        out.append(text[pos:m.start()])
        tag = m.group(0)
        name = m.group(1).lower()
        closing = tag.startswith("</")
        if name in ("strong", "b"):
            out.append("**" if not closing else "**")
        elif name in ("em", "i"):
            out.append("*" if not closing else "*")
        elif name == "code":
            out.append("`" if not closing else "`")
        elif name in ("p",):
            out.append("\n\n")
        elif name == "br":
            out.append("  \n")
        elif name == "hr":
            out.append("\n---\n")
        elif name in ("ul", "ol"):
            # list container tags -> nothing in markdown
            pass
        elif name == "li":
            out.append("\n- " if not closing else "")
        elif name == "blockquote":
            out.append("\n> " if not closing else "\n")
        elif re.fullmatch(r"h[1-6]", name):
            level = int(name[1])
            out.append(("\n\n" + "#" * level + " ") if not closing else "\n\n")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _convert_inline_html(text: str) -> str:
    """Convert the HTML fragments HTB embeds in markdown bodies.

    Order matters: resolve nested content (links inside alerts inside cards)
    before their parents, then handle block structure, then inline tags."""
    text = _convert_links(text)          # <a> may contain inline tags
    text = _convert_alerts(text)         # alert boxes (note/warning)
    text = _convert_cards(text)          # card-body containers
    text = _IMG_RE.sub(lambda m: _convert_img_tag(m.group(0)), text)
    text = _convert_simple_tags(text)    # strong/em/code/p/br/hr/li/headings
    text = _html.unescape(text)          # &amp; &lt; &gt; etc.
    return text


def content_to_markdown(content: str) -> str:
    """Full pipeline: HTB section body -> clean Markdown (no image rewriting).

    The content is mostly Markdown with embedded HTML fragments. We normalize
    HTB-specific code quirks, then convert only the HTML fragments outside
    fenced code blocks, preserving all the surrounding Markdown verbatim."""
    if not content:
        return ""

    md = content.replace("\r\n", "\n").replace("\r", "\n")
    md = _normalize_code_quirks(md)
    md = _deindent_fences(md)

    # Convert HTML fragments only in non-code chunks.
    chunks = _split_code_and_text(md)
    rebuilt = []
    for is_code, chunk in chunks:
        rebuilt.append(chunk if is_code else _convert_inline_html(chunk))
    md = "\n".join(rebuilt)

    md = _collapse_blanks(md)
    # Trim trailing whitespace on every line (HTML tag removal often leaves
    # stray "  " runs), then drop lines that are now only whitespace.
    md = "\n".join(line.rstrip() for line in md.split("\n"))
    md = re.sub(r"^[ \t]+$", "", md, flags=re.MULTILINE)
    # Normalize list bullets to '-'.
    md = re.sub(r"^\s*[+*]\s", "- ", md, flags=re.MULTILINE)
    md = _collapse_blanks(md)
    return md.strip() + "\n"


# ---------------------------------------------------------------------------
# 2. Image handling
# ---------------------------------------------------------------------------

_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def resolve_image_url(src: str) -> str:
    """Turn a possibly-relative image src into an absolute URL."""
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/content/"):
        return CDN_BASE + src
    return HTB_BASE + src


def _cdn_fallback_url(url: str) -> str | None:
    """Alternative URL to try if the primary 404s."""
    if HTB_BASE not in url:
        return None
    parsed = urlparse(url)
    cdn_path = parsed.path.replace("/storage/", "/content/", 1)
    return f"{parsed.scheme}://{parsed.hostname}{cdn_path}"


# Most Linux and macOS filesystems cap a single path component at 255 bytes.
_NAME_MAX_BYTES = 255


def _safe_filename(url: str) -> str:
    """Stable, filesystem-safe name derived from the image URL."""
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or "image"
    # If HTB didn't give us an extension, guess .png for image assets.
    if "." not in name:
        name += ".png"
    # Disambiguate with a short hash of the full URL so different paths that
    # share a basename don't collide.
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    stem, ext = os.path.splitext(name)
    # Mermaid diagrams arrive as mermaid.ink/img/pako:<the whole compressed
    # diagram>, so the basename alone can blow past the filesystem's 255-byte
    # NAME_MAX and make every path call raise OSError. The digest already keeps
    # the name unique, so the stem is only a readability hint: truncate it.
    # Slice bytes, not characters, since a non-ASCII basename can be wider.
    budget = _NAME_MAX_BYTES - len(f"-{digest}{ext}".encode("utf-8"))
    stem_bytes = stem.encode("utf-8")[:budget]
    stem = stem_bytes.decode("utf-8", "ignore") or "image"
    return f"{stem}-{digest}{ext}"


def download_image(
    url: str,
    assets_dir: Path,
    session: requests.Session,
    cookie: str,
    timeout: int = 30,
    referer: str = HTB_BASE + "/",
) -> Path | None:
    """Download one image into assets_dir. Returns the local path, or None on
    failure after trying the CDN fallback."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(url)
    dest = assets_dir / filename
    if dest.exists():
        return dest

    headers = {
        "Cookie": cookie,
        "Referer": referer,
        "User-Agent": USER_AGENT,
    }

    candidates = [url]
    fallback = _cdn_fallback_url(url)
    if fallback:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            resp = session.get(candidate, headers=headers, timeout=timeout)
        except requests.RequestException:
            time.sleep(0.5)
            continue
        if resp.status_code == 200 and resp.content:
            try:
                dest.write_bytes(resp.content)
            except OSError:
                # One unwritable asset shouldn't abort a whole module; the
                # caller keeps the remote link when we return None.
                return None
            return dest
    return None


def rewrite_images(
    md: str,
    assets_dir: Path,
    session: requests.Session,
    cookie: str,
    quiet: bool = False,
) -> str:
    """Find every Markdown image, download it, and rewrite the link to the local
    relative path. Runs only outside fenced code blocks."""
    chunks = _split_code_and_text(md)
    out = []
    for is_code, chunk in chunks:
        if is_code:
            out.append(chunk)
            continue

        def repl(m: re.Match) -> str:
            alt, src = m.group(1), m.group(2).strip()
            absolute = resolve_image_url(src)
            local = download_image(absolute, assets_dir, session, cookie)
            if local is None:
                # Keep the remote link so the user at least sees what failed.
                return f"![{alt}]({absolute})"
            rel = Path("assets") / local.name
            return f"![{alt}]({rel.as_posix()})"

        out.append(_MD_IMG_RE.sub(repl, chunk))
    return "\n".join(out)
