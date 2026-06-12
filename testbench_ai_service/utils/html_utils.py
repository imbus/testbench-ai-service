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
