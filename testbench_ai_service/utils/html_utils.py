from html.parser import HTMLParser


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


class HTMLBodyTextExtractor(HTMLParser):
    """
    Extracts visible text from the `<body>` of HTML, skipping `<script>` and `<style>` tags.
    """

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._in_body: bool = False
        self._skip: bool = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if self._in_body and not self._skip:
            self.text_parts.append(data)

    def get_text(self) -> str:
        return "".join(self.text_parts).strip()


def extract_text_from_html_body(html: str) -> str:
    """
    Extracts and returns visible text only from the <body> of an HTML string.
    """
    parser = HTMLBodyTextExtractor()
    parser.feed(html)
    return parser.get_text()
