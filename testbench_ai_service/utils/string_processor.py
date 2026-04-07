import re
from html.parser import HTMLParser


async def remove_html_from_string(
    text: str, preserve_important_tags: bool = False, preserve_all_line_breaks: bool = False
) -> str:
    """Removes HTML elements from a given string.

    Args:
        text: The input string containing HTML content.
        preserve_important_tags: If True, preserves important tags such as <b>, <i>, and <u>.
            Edit important tags in the list below.
        preserve_all_line_breaks: If True, retains all line breaks in the input text.
            If False, line breaks longer than two consecutive lines are reduced to a maximum of two.

    Returns:
        The processed string with HTML elements removed. Custom non-HTML (e.g. XML) tags are not removed.

    Raises:
        ValueError: If the input `text` is not a string.
    """
    # Use '*' to mark tags that should be preserved when 'preserve_important_tags' is True
    html_tags = [
        ("!--", ""),
        ("!DOCTYPE", ""),
        ("a", ""),
        ("abbr", ""),
        ("acronym", ""),
        ("address", ""),
        ("applet", ""),
        ("area", ""),
        ("article", ""),
        ("aside", ""),
        ("audio", ""),
        ("b", "*"),
        ("base", ""),
        ("basefont", ""),
        ("bdi", ""),
        ("bdo", ""),
        ("big", ""),
        ("blockquote", ""),
        ("body", ""),
        ("br", "*"),
        ("button", ""),
        ("canvas", ""),
        ("caption", ""),
        ("center", ""),
        ("cite", ""),
        ("code", "*"),
        ("col", "*"),
        ("colgroup", "*"),
        ("data", ""),
        ("datalist", ""),
        ("dd", "*"),
        ("del", "*"),
        ("details", ""),
        ("dfn", ""),
        ("dialog", ""),
        ("dir", ""),
        ("div", ""),
        ("dl", "*"),
        ("dt", "*"),
        ("em", "*"),
        ("embed", ""),
        ("fieldset", ""),
        ("figcaption", "*"),
        ("figure", ""),
        ("font", ""),
        ("footer", ""),
        ("form", ""),
        ("frame", ""),
        ("frameset", ""),
        ("h1", "*"),
        ("h2", "*"),
        ("h3", "*"),
        ("h4", "*"),
        ("h5", "*"),
        ("h6", "*"),
        ("head", ""),
        ("header", ""),
        ("hgroup", ""),
        ("hr", ""),
        ("html", ""),
        ("i", "*"),
        ("iframe", ""),
        ("img", ""),
        ("input", ""),
        ("ins", "*"),
        ("kbd", ""),
        ("label", ""),
        ("legend", ""),
        ("li", ""),
        ("link", "*"),
        ("main", ""),
        ("map", ""),
        ("mark", "*"),
        ("menu", ""),
        ("meta", ""),
        ("meter", ""),
        ("nav", ""),
        ("noframes", ""),
        ("noscript", ""),
        ("object", ""),
        ("ol", "*"),
        ("optgroup", ""),
        ("option", ""),
        ("output", ""),
        ("p", ""),
        ("param", ""),
        ("picture", ""),
        ("pre", ""),
        ("progress", ""),
        ("q", ""),
        ("rp", ""),
        ("rt", ""),
        ("ruby", ""),
        ("s", "*"),
        ("samp", ""),
        ("script", ""),
        ("search", ""),
        ("section", ""),
        ("select", ""),
        ("small", ""),
        ("source", ""),
        ("span", ""),
        ("strike", "*"),
        ("strong", "*"),
        ("style", ""),
        ("sub", "*"),
        ("summary", ""),
        ("sup", "*"),
        ("svg", ""),
        ("table", "*"),
        ("tbody", ""),
        ("td", "*"),
        ("template", ""),
        ("textarea", ""),
        ("tfoot", "*"),
        ("th", "*"),
        ("thead", ""),
        ("time", ""),
        ("title", ""),
        ("tr", ""),
        ("track", ""),
        ("tt", ""),
        ("u", "*"),
        ("ul", "*"),
        ("var", ""),
        ("video", ""),
        ("wbr", ""),
    ]

    # Check if input is string
    if not isinstance(text, str):
        raise ValueError("Input must be a string")

    # Check if input is empty or contains only whitespaces
    if not text.strip() or text.isspace():
        return ""

    # Remove html (optionally preserve important tags)
    if preserve_important_tags:
        removal_tags = [tag for tag, flag in html_tags if flag == ""]
    else:
        removal_tags = [tag for tag, flag in html_tags]
    tags_pattern = "|".join(removal_tags)  # Creates a string in format: a|abbr|address...
    html_pattern = re.compile(
        rf"</?({tags_pattern})(\s[^>]*?)?/?>", re.IGNORECASE
    )  # Creates the regular expression
    clean_text = re.sub(html_pattern, "", text)

    # REGEX EXPLANATION:
    # < matches the opening < of an HTML tag
    # /? optionally matches a / for closing tags (e.g., </div>)
    # ({tags_pattern}) matches any tag name from the removal_tags list
    # \\s matches any whitespace character
    # [^>]*? matches any number of characters that are not >
    # (...)? makes the entire group optional, meaning that tags without attributes are also matched
    # /? matches an optional /, used in self-closing tags
    # > matches the closing > of an HTML tag
    # re.IGNORECASE makes the regular expression case-insensitive (e.g., matching <DIV> and <div>)

    # TODO: Replace <br> with \n?
    # TODO: Remove trailing whitespaces?

    # Trim line breaks
    if not preserve_all_line_breaks:
        clean_text = await _remove_excess_line_breaks(clean_text)

    return clean_text


async def _remove_excess_line_breaks(text: str) -> str:
    """Trims consecutive line breaks to a maximum of two.
    For example, four consecutive line breaks ("\n\n\n\n") will be replaced with two ("\n\n").
    """
    pattern = re.compile(
        r"[ \t]*\n(?:[ \t]*\n)+"
    )  # Also removes trailing whitespace before line breaks
    return re.sub(pattern, "\n\n", text)


def add_testbench_html(text: str) -> str:
    """Readds the destinct html of the testbench back to them string."""
    return "<html><body>\n" + text + "\n</body></html>"


def strip_html_body_tags(text: str) -> str:
    """
    Remove all occurrences of <html>, </html>, <body>, and </body> tags from the input text.
    """
    return (
        text.replace("<html>", "")
        .replace("</html>", "")
        .replace("<body>", "")
        .replace("</body>", "")
    )


class HTMLBodyTextExtractor(HTMLParser):
    """
    Extracts visible text from the <body> of HTML, skipping <script> and <style> tags.
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
