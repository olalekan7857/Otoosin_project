"""Safe rendering for the plain-text body copy stored by legal documents.

Administrators edit plain text, never raw HTML. The renderer escapes every
character first and then adds only the small set of tags the public policy
design needs (paragraphs, line breaks, lists, bold text and links).

Formatting supported in the admin textareas:

* Blank lines separate paragraphs.
* Lines beginning with ``- `` or ``* `` form a bulleted list.
* Lines beginning with ``1. `` (or any number) form a numbered list.
* ``**text**`` renders bold text.
* ``[label](/path/)`` renders a link. Relative paths and http(s)/mailto URLs
  are allowed; other schemes are discarded.
* A paragraph that contains nothing but a link renders as a button.
"""

import re
from html import escape
from urllib.parse import urlsplit

from django.utils.safestring import mark_safe


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ORDERED_RE = re.compile(r"^\d+[.)]\s+")


def _safe_href(value):
    href = (value or "").strip()
    parsed = urlsplit(href)
    scheme = parsed.scheme.lower()
    if href.startswith("//"):
        return ""
    if scheme and scheme not in {"http", "https", "mailto"}:
        return ""
    if scheme in {"http", "https"} and not parsed.netloc:
        return ""
    if not scheme and not href.startswith(("/", "#", "?")):
        return ""
    return href


def _inline(value, button=False):
    """Escape ``value`` and add the permitted inline markup."""
    text = escape(value, quote=False)

    def link(match):
        label = match.group(1)
        href = _safe_href(match.group(2).replace("&amp;", "&"))
        if not href:
            return label
        css = ' class="vs-btn"' if button else ""
        return f'<a{css} href="{escape(href, quote=True)}">{label}</a>'

    text = _LINK_RE.sub(link, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    return text


def _bullet_text(line):
    stripped = line.strip()
    if stripped.startswith(("- ", "* ")):
        return stripped[2:].strip()
    return None


def _ordered_text(line):
    stripped = line.strip()
    if _ORDERED_RE.match(stripped):
        return _ORDERED_RE.sub("", stripped).strip()
    return None


def render_legal_text(value):
    """Return escaped HTML for the stored plain-text body copy."""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return mark_safe("")

    parts = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        index = 0
        while index < len(lines):
            bullet = _bullet_text(lines[index])
            ordered = _ordered_text(lines[index])

            if bullet is not None:
                items = []
                while index < len(lines):
                    item = _bullet_text(lines[index])
                    if item is None:
                        break
                    items.append(item)
                    index += 1
                parts.append(
                    "<ul>"
                    + "".join(f"<li>{_inline(item)}</li>" for item in items)
                    + "</ul>"
                )
            elif ordered is not None:
                items = []
                while index < len(lines):
                    item = _ordered_text(lines[index])
                    if item is None:
                        break
                    items.append(item)
                    index += 1
                parts.append(
                    "<ol>"
                    + "".join(f"<li>{_inline(item)}</li>" for item in items)
                    + "</ol>"
                )
            else:
                paragraph = []
                while index < len(lines):
                    if (
                        _bullet_text(lines[index]) is not None
                        or _ordered_text(lines[index]) is not None
                    ):
                        break
                    paragraph.append(lines[index])
                    index += 1
                only_link = (
                    len(paragraph) == 1
                    and _LINK_RE.fullmatch(paragraph[0])
                )
                body = "<br>".join(
                    _inline(line, button=only_link) for line in paragraph
                )
                parts.append(f"<p>{body}</p>")

    return mark_safe("".join(parts))
