import re
from html import escape
from html.parser import HTMLParser


class HTMLBodyTextExtractor(HTMLParser):
    """
    Extracts visible text from an HTML string.

    By default, only collects text inside the ``<body>`` tag. Pass
    ``fragment_mode=True`` to treat the entire input as body content,
    which is useful for bare HTML fragments that have no ``<body>`` tag.

    Tags listed in `SKIP_TAGS` (script, style, head, etc.) are always
    excluded, regardless of mode. Nested skip-tags are handled correctly
    via a depth counter rather than a simple boolean flag.
    """

    SKIP_TAGS = frozenset({"script", "style", "head", "title", "meta", "noscript"})

    def __init__(self, fragment_mode: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self._in_body: bool = fragment_mode
        self._has_body: bool = False
        self._skip_depth: int = 0

    @property
    def has_body(self) -> bool:
        return self._has_body

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "body":
            self._in_body = True
            self._has_body = True
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_body and self._skip_depth == 0:
            self.text_parts.append(data)

    def get_text(self) -> str:
        return "".join(self.text_parts).strip()


def extract_text_from_html_body(html: str) -> str:
    """
    Extracts and returns visible text only from the ``<body>`` of an HTML string.

    Returns an empty string if no ``<body>`` tag is present.
    For bare fragments, use ``has_visible_text`` or instantiate
    ``HTMLBodyTextExtractor(fragment_mode=True)`` directly.
    """
    parser = HTMLBodyTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def has_visible_text(html: str) -> bool:
    """
    Returns True if the HTML string contains any visible (non-whitespace) text.

    Works for both full HTML documents and bare fragments without a ``<body>`` tag.
    Falls back to fragment mode when no ``<body>`` tag is detected.
    """
    parser = HTMLBodyTextExtractor()
    parser.feed(html)
    parser.close()

    if not parser.has_body:
        fragment_parser = HTMLBodyTextExtractor(fragment_mode=True)
        fragment_parser.feed(html)
        fragment_parser.close()
        return bool(fragment_parser.get_text())

    return bool(parser.get_text())


def add_html_body_tags(html: str) -> str:
    """
    Wraps the input HTML string in `<html><body>...</body></html>` tags if they are not already present.
    """
    if "<html" in html.lower() and "<body" in html.lower():
        return html
    return f"<html><body>{html}</body></html>"


def strip_html_body_tags(text: str) -> str:
    """
    Remove all occurrences of `<html>`, `</html>`, `<body>`, and `</body>` tags from the input text.
    """
    return (
        text.replace("<html>", "")
        .replace("</html>", "")
        .replace("<body>", "")
        .replace("</body>", "")
    )


def build_disclaimer_html(disclaimer_text: str) -> str:
    """
    Wraps disclaimer text in the standard styled disclaimer block.
    """
    return (
        f"<div style='padding-top: 5px;'>"
        f"<div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>"
        f"{disclaimer_text}</div></div>"
    )


def escape_html(text: str) -> str:
    """
    Escapes special HTML characters and converts newlines to <br/> tags.
    """
    return escape(text).replace("\n", "<br/>")


HTML_HEADER = re.compile(r"<head\b[^>]*>.*?</head\s*>", re.DOTALL | re.IGNORECASE)


def visible_text(html: str) -> str:
    """Return the visible text of an HTML document or fragment, whitespace collapsed.

    A ``<head>`` is left out, so styles and titles do not read as content.
    """
    without_head = HTML_HEADER.sub("", html)
    text = extract_text_from_html_body(add_html_body_tags(without_head))
    return " ".join(text.split())


#: The start of any tag or comment; text without one is not HTML.
HTML_TAG = re.compile(r"<[a-zA-Z/!]")


class HTMLStructuredTextExtractor(HTMLParser):
    """Turns HTML into plain text that keeps line breaks, lists and tables.

    Everything else is reduced to its text: inline tags, attributes and comments
    vanish, and the tags in `SKIP_TAGS` vanish together with their content.
    """

    SKIP_TAGS = frozenset({"script", "style", "head", "title", "noscript", "template"})
    #: Tags that start and end a paragraph: a line of their own, set off by a blank line.
    BLOCK_TAGS = frozenset(
        {
            "p", "div", "section", "article", "blockquote", "header", "footer", "main",
            "aside", "figure", "figcaption", "form", "fieldset", "address", "dl", "details",
            "summary", "hr",
        }
    )  # fmt: skip
    #: Tags that only start and end a line.
    LINE_TAGS = frozenset({"dt", "dd", "caption"})
    HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
    VOID_TAGS = frozenset({"br", "img"})
    LIST_TAGS = frozenset({"ul", "ol", "li"})
    TABLE_TAGS = frozenset({"table", "tr", "td", "th"})

    #: Marks a line break inside a table cell until the cell is joined into one line.
    _CELL_BREAK = "\x00"

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._line: list[str] = []
        self._blank_pending = False
        self._skip_depth = 0
        self._pre_depth = 0
        self._heading = False
        #: Open lists, innermost last: the tag and the next number of an ordered list.
        self._lists: list[tuple[str, int]] = []
        self._marker: str | None = None
        self._table_depth = 0
        self._first_row = False
        self._row: list[str] | None = None
        self._row_tags: set[str] = set()
        self._cell: list[str] | None = None

    def _emit(self, text: str) -> None:
        if self._blank_pending and self._lines:
            self._lines.append("")
        self._blank_pending = False
        depth = len(self._lists)
        if self._marker is not None:
            prefix = "  " * max(depth - 1, 0) + self._marker
            self._marker = None
        else:
            prefix = "  " * depth
        self._lines.append(f"{prefix}{'## ' if self._heading else ''}{text}")

    def _flush(self) -> bool:
        """End the current line; returns whether it held any text."""
        if self._cell is not None:
            self._cell.append(self._CELL_BREAK)
            return False
        text = "".join(self._line)
        self._line = []
        text = text.rstrip() if self._pre_depth else " ".join(text.split())
        if not text.strip():
            return False
        self._emit(text)
        return True

    def _block(self) -> None:
        """End the current line and separate what follows by a blank line."""
        self._flush()
        if self._cell is None and not self._lists:
            self._blank_pending = True

    def _close_cell(self) -> None:
        if self._cell is None:
            return
        parts = (" ".join(part.split()) for part in "".join(self._cell).split(self._CELL_BREAK))
        self._cell = None
        if self._row is not None:
            self._row.append(" / ".join(part for part in parts if part))

    def _close_row(self) -> None:
        self._close_cell()
        row, self._row = self._row, None
        if not row or not any(row):
            return
        self._flush()
        self._emit(" | ".join(row))
        if self._first_row and self._row_tags == {"th"} and len(row) > 1:
            self._emit(" | ".join(["---"] * len(row)))
        self._first_row = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.LIST_TAGS:
            self._start_list_tag(tag, attrs)
        elif tag in self.TABLE_TAGS:
            self._start_table_tag(tag)
        elif tag in self.VOID_TAGS:
            self._void_tag(tag, attrs)
        elif tag in self.BLOCK_TAGS:
            self._block()
        elif tag in self.LINE_TAGS:
            self._flush()
        elif tag in self.HEADING_TAGS:
            self._block()
            self._heading = self._cell is None
        elif tag == "pre":
            self._block()
            self._pre_depth += 1

    def _void_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            # A break on an empty line is a second break in a row: a blank line.
            if not self._flush() and self._cell is None and not self._lists:
                self._blank_pending = True
        elif alt := (dict(attrs).get("alt") or "").strip():
            self.handle_data(f"[image: {alt}]")

    def _start_list_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "li":
            self._block()
            start = dict(attrs).get("start") or ""
            self._lists.append((tag, int(start) if start.isdigit() else 1))
            return
        self._flush()
        if self._cell is not None:
            return
        self._marker = "- "
        if self._lists and self._lists[-1][0] == "ol":
            number = self._lists[-1][1]
            self._marker = f"{number}. "
            self._lists[-1] = ("ol", number + 1)

    def _end_list_tag(self, tag: str) -> None:
        self._flush()
        if tag == "li":
            if self._cell is None:
                self._marker = None
            return
        if self._lists:
            self._lists.pop()
        self._marker = None
        self._block()

    def _start_table_tag(self, tag: str) -> None:
        if tag == "table":
            self._block()
            self._table_depth += 1
            if self._table_depth == 1:
                self._first_row = True
        elif self._table_depth != 1:
            # Outside a table, or in a nested one that is flattened into its cell.
            self._flush()
        elif tag == "tr":
            self._close_row()
            self._row, self._row_tags = [], set()
        else:
            self._close_cell()
            if self._row is None:
                self._row, self._row_tags = [], set()
            self._row_tags.add(tag)
            self._cell = []

    def _end_table_tag(self, tag: str) -> None:
        if tag == "table":
            if self._table_depth == 1:
                self._close_row()
            self._table_depth = max(self._table_depth - 1, 0)
            self._block()
        elif self._table_depth != 1:
            self._flush()
        elif tag == "tr":
            self._close_row()
        else:
            self._close_cell()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(self._skip_depth - 1, 0)
            return
        if self._skip_depth:
            return
        if tag in self.LIST_TAGS:
            self._end_list_tag(tag)
        elif tag in self.TABLE_TAGS:
            self._end_table_tag(tag)
        elif tag in self.BLOCK_TAGS:
            self._block()
        elif tag in self.LINE_TAGS:
            self._flush()
        elif tag in self.HEADING_TAGS:
            self._flush()
            self._heading = False
            self._block()
        elif tag == "pre":
            self._flush()
            self._pre_depth = max(self._pre_depth - 1, 0)
            self._block()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data.replace(self._CELL_BREAK, ""))
        elif self._pre_depth:
            for number, part in enumerate(data.replace("\xa0", " ").split("\n")):
                if number:
                    self._flush()
                self._line.append(part)
        elif not self._table_depth or data.strip():
            self._line.append(data)

    def get_text(self) -> str:
        self._close_row()
        self._flush()
        return "\n".join(self._lines)


def html_to_structured_text(html: str) -> str:
    """Return an HTML document or fragment as plain text that keeps its structure.

    Paragraphs and ``<br>`` become line breaks, headings a ``## `` line, list items
    ``- `` or ``1. `` lines (nested ones indented), table rows ``a | b`` lines with a
    ``---`` row below a header row, and a ``<pre>`` keeps its lines. Every other tag
    is dropped and its text kept; scripts, styles, the ``<head>`` and comments are
    dropped with their content. Returns an empty string when nothing is visible.

    Text without any tag is taken as plain text, whose own line breaks are kept.
    """
    if not HTML_TAG.search(html):
        html = f"<pre>{html}</pre>"
    parser = HTMLStructuredTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()
