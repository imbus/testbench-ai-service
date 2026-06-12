from testbench_ai_service.utils.html_utils import (
    extract_text_from_html_body,
    strip_html_body_tags,
)


class TestStripHtmlBodyTags:
    """strip_html_body_tags removes <html>, </html>, <body>, and </body> tags."""

    def test_empty_string_returns_empty(self):
        assert strip_html_body_tags("") == ""

    def test_plain_text_is_unchanged(self):
        assert strip_html_body_tags("Hello world") == "Hello world"

    def test_removes_opening_html_tag(self):
        assert strip_html_body_tags("<html>content") == "content"

    def test_removes_closing_html_tag(self):
        assert strip_html_body_tags("content</html>") == "content"

    def test_removes_opening_body_tag(self):
        assert strip_html_body_tags("<body>content") == "content"

    def test_removes_closing_body_tag(self):
        assert strip_html_body_tags("content</body>") == "content"

    def test_removes_all_wrapper_tags(self):
        assert strip_html_body_tags("<html><body>content</body></html>") == "content"

    def test_other_tags_are_preserved(self):
        result = strip_html_body_tags("<html><body><p>Hello</p></body></html>")
        assert result == "<p>Hello</p>"

    def test_multiple_occurrences_are_all_removed(self):
        result = strip_html_body_tags("<html><html>text</html></html>")
        assert result == "text"


class TestExtractTextFromHtmlBody:
    """extract_text_from_html_body returns visible text from the <body> element."""

    def test_empty_string_returns_empty(self):
        assert extract_text_from_html_body("") == ""

    def test_plain_text_outside_body_returns_empty(self):
        assert extract_text_from_html_body("<html><head><title>T</title></head></html>") == ""

    def test_extracts_text_from_body(self):
        result = extract_text_from_html_body("<html><body>Hello world</body></html>")
        assert result == "Hello world"

    def test_extracts_text_from_nested_tags(self):
        result = extract_text_from_html_body("<body><p>Hello <b>world</b>!</p></body>")
        assert result == "Hello world!"

    def test_skips_script_tag_content(self):
        result = extract_text_from_html_body(
            "<body>Visible<script>alert('hidden')</script>text</body>"
        )
        assert result == "Visibletext"

    def test_skips_style_tag_content(self):
        result = extract_text_from_html_body(
            "<body>Visible<style>.hidden { display: none; }</style>text</body>"
        )
        assert result == "Visibletext"

    def test_whitespace_is_stripped_from_result(self):
        result = extract_text_from_html_body("<body>   Hello   </body>")
        assert result == "Hello"

    def test_no_body_tag_returns_empty(self):
        assert extract_text_from_html_body("<p>No body here</p>") == ""
