from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
import re

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_UNORDERED_LIST_PATTERN = re.compile(r"^(\s*)-\s+(.*)$")
_ORDERED_LIST_PATTERN = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_CODE_FENCE_PATTERN = re.compile(r"^```([\w+-]*)\s*$")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")


def get_api_spec_path() -> Path:
    return Path(__file__).resolve().parent.parent / "API_SPEC.md"


@lru_cache
def load_api_spec_html() -> str:
    return render_markdown_document(get_api_spec_path().read_text(encoding="utf-8"))


def render_markdown_document(markdown: str) -> str:
    lines = markdown.splitlines()
    html_parts: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        if _CODE_FENCE_PATTERN.match(line):
            block_html, index = _render_code_block(lines, index)
            html_parts.append(block_html)
            continue

        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            hashes, title = heading_match.groups()
            level = len(hashes)
            anchor = _slugify(title)
            html_parts.append(
                f'<h{level} id="{anchor}">{_render_inline(title.strip())}</h{level}>'
            )
            index += 1
            continue

        if _is_table_start(lines, index):
            block_html, index = _render_table_block(lines, index)
            html_parts.append(block_html)
            continue

        if _match_list_item(line):
            block_html, index = _render_list_block(lines, index)
            html_parts.append(block_html)
            continue

        block_html, index = _render_paragraph(lines, index)
        html_parts.append(block_html)

    return "\n".join(html_parts)


def _render_code_block(lines: list[str], start: int) -> tuple[str, int]:
    opening_match = _CODE_FENCE_PATTERN.match(lines[start].strip())
    language = opening_match.group(1) if opening_match else ""
    index = start + 1
    code_lines: list[str] = []

    while index < len(lines) and not _CODE_FENCE_PATTERN.match(lines[index].strip()):
        code_lines.append(lines[index])
        index += 1

    if index < len(lines):
        index += 1

    class_attr = f' class="language-{escape(language)}"' if language else ""
    code = escape("\n".join(code_lines))
    return f"<pre><code{class_attr}>{code}</code></pre>", index


def _render_table_block(lines: list[str], start: int) -> tuple[str, int]:
    index = start
    table_lines: list[str] = []
    while index < len(lines) and lines[index].strip().startswith("|"):
        table_lines.append(lines[index].strip())
        index += 1

    header_cells = _split_table_row(table_lines[0])
    body_lines = table_lines[2:] if len(table_lines) >= 2 else []

    header_html = "".join(f"<th>{_render_inline(cell)}</th>" for cell in header_cells)
    body_rows = []
    for row in body_lines:
        cells = _split_table_row(row)
        body_rows.append(
            "<tr>"
            + "".join(f"<td>{_render_inline(cell)}</td>" for cell in cells)
            + "</tr>"
        )

    body_html = f"<tbody>{''.join(body_rows)}</tbody>" if body_rows else ""
    html = (
        '<div class="table-wrap markdown-table">'
        "<table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"{body_html}"
        "</table>"
        "</div>"
    )
    return html, index


def _render_list_block(lines: list[str], start: int) -> tuple[str, int]:
    first_match = _match_list_item(lines[start])
    list_tag = "ol" if first_match and first_match["type"] == "ol" else "ul"
    items: list[str] = []
    index = start

    while index < len(lines):
        line = lines[index]
        match = _match_list_item(line)
        if match is None:
            if not line.strip():
                index += 1
            break
        if match["type"] != list_tag:
            break

        text_parts = [match["text"]]
        index += 1
        while index < len(lines):
            continuation = lines[index]
            if not continuation.strip():
                break
            if _is_block_start(lines, index) or _match_list_item(continuation):
                break
            text_parts.append(continuation.strip())
            index += 1

        depth = min(match["depth"], 5)
        items.append(
            f'<li class="md-depth-{depth}">{_render_inline(" ".join(text_parts).strip())}</li>'
        )

    html = f'<{list_tag} class="md-list md-list-{list_tag}">{"".join(items)}</{list_tag}>'
    return html, index


def _render_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    paragraph_lines: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if index != start and _is_block_start(lines, index):
            break
        paragraph_lines.append(line)
        index += 1

    text = _join_paragraph_lines(paragraph_lines)
    return f"<p>{text}</p>", index


def _join_paragraph_lines(lines: list[str]) -> str:
    if not lines:
        return ""

    fragments = [_render_inline(lines[0].strip())]
    for previous, current in zip(lines, lines[1:]):
        joiner = "<br>" if previous.endswith("  ") else " "
        fragments.append(joiner)
        fragments.append(_render_inline(current.strip()))
    return "".join(fragments)


def _render_inline(text: str) -> str:
    parts: list[str] = []
    last_index = 0
    for match in _INLINE_CODE_PATTERN.finditer(text):
        parts.append(escape(text[last_index : match.start()]))
        parts.append(f"<code>{escape(match.group(1))}</code>")
        last_index = match.end()
    parts.append(escape(text[last_index:]))
    return "".join(parts)


def _match_list_item(line: str) -> dict[str, str | int] | None:
    unordered_match = _UNORDERED_LIST_PATTERN.match(line)
    if unordered_match:
        indent, text = unordered_match.groups()
        return {"type": "ul", "depth": len(indent) // 2, "text": text.strip()}

    ordered_match = _ORDERED_LIST_PATTERN.match(line)
    if ordered_match:
        indent, _number, text = ordered_match.groups()
        return {"type": "ol", "depth": len(indent) // 2, "text": text.strip()}

    return None


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = lines[index].strip()
    separator = lines[index + 1].strip()
    return current.startswith("|") and _TABLE_SEPARATOR_PATTERN.match(separator) is not None


def _is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    stripped = line.strip()
    if not stripped:
        return True
    return any(
        (
            _CODE_FENCE_PATTERN.match(stripped),
            _HEADING_PATTERN.match(stripped),
            _is_table_start(lines, index),
            _match_list_item(line),
        )
    )


def _split_table_row(row: str) -> list[str]:
    stripped = row.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "section"
