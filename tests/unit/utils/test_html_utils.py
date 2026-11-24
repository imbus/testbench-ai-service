from testbench_ai_service.utils.html_utils import (
    extract_text_from_html_body,
    html_to_structured_text,
    strip_html_body_tags,
    visible_text,
)


class TestHtmlToStructuredText:
    def test_paragraphs_and_breaks_become_lines(self):
        html = "<p>First<br/>second</p><p>Third</p><div>Fourth</div>"

        assert html_to_structured_text(html) == "First\nsecond\n\nThird\n\nFourth"

    def test_inline_tags_attributes_and_entities_leave_only_text(self):
        html = (
            '<p class="x" style="color:red">A <b>bold</b>&nbsp;<span>&amp; <i>plain</i></span></p>'
        )

        assert html_to_structured_text(html) == "A bold & plain"

    def test_scripts_styles_head_and_comments_are_dropped_with_content(self):
        html = (
            "<html><head><meta charset='utf-8'><title>T</title><style>p {}</style></head>"
            "<body><!-- hidden --><script>alert(1)</script><p>Visible</p></body></html>"
        )

        assert html_to_structured_text(html) == "Visible"

    def test_lists_keep_markers_numbers_and_nesting(self):
        html = (
            "<p>Rules:</p><ul><li>One</li><li>Two<ol><li>Sub a</li><li>Sub b</li></ol></li></ul>"
            '<ol start="3"><li><p>Three</p></li><li>Four</li></ol>'
        )

        assert html_to_structured_text(html) == (
            "Rules:\n\n- One\n- Two\n  1. Sub a\n  2. Sub b\n\n3. Three\n4. Four"
        )

    def test_a_table_becomes_rows_with_a_rule_below_the_header(self):
        html = (
            "<table><thead><tr><th>Role</th><th>Access</th></tr></thead><tbody>"
            "<tr><td>Admin</td><td><p>read</p><p>write</p></td></tr>"
            "<tr><td>Guest</td><td></td></tr></tbody></table><p>After</p>"
        )

        assert html_to_structured_text(html) == (
            "Role | Access\n--- | ---\nAdmin | read / write\nGuest | \n\nAfter"
        )

    def test_a_table_without_header_cells_has_no_rule(self):
        assert html_to_structured_text("<table><tr><td>a</td><td>b</td></tr></table>") == "a | b"

    def test_a_nested_table_is_flattened_into_its_cell(self):
        html = "<table><tr><td>a</td><td><table><tr><td>x</td><td>y</td></tr></table></td></tr></table>"

        assert html_to_structured_text(html) == "a | x / y"

    def test_headings_pre_and_images(self):
        html = (
            '<h2>Scope</h2><pre>if a:\n    b()</pre><img src="x.png" alt="Flow"><img src="y.png">'
        )

        assert html_to_structured_text(html) == "## Scope\n\nif a:\n    b()\n\n[image: Flow]"

    def test_plain_text_keeps_its_own_lines(self):
        assert html_to_structured_text("Orders above 100 EUR\n  get 5 % off.") == (
            "Orders above 100 EUR\n  get 5 % off."
        )

    def test_nothing_visible_is_an_empty_string(self):
        assert html_to_structured_text("<p> </p><br/>") == ""
        assert html_to_structured_text("") == ""


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


def test_visible_text_leaves_out_the_head():
    html = (
        "<html><head><style>p { color: red }</style></head><body><p>Login  works</p></body></html>"
    )

    assert visible_text(html) == "Login works"


def test_visible_text_reads_a_bare_fragment():
    assert visible_text("<p>Nach 3 <b>Fehlversuchen</b></p>") == "Nach 3 Fehlversuchen"
