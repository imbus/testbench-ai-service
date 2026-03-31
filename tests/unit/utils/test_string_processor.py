import unittest

from testbench_ai_service.utils.string_processor import remove_html_from_string


class TestRemoveHtmlFromString(unittest.IsolatedAsyncioTestCase):
    """remove_html_from_string strips or preserves HTML depending on configuration."""

    async def test_empty_string_returns_empty(self):
        self.assertEqual(await remove_html_from_string(""), "")

    async def test_whitespace_only_string_returns_empty(self):
        result = await remove_html_from_string("                    \n\n    \n   \n")
        self.assertEqual(result, "")

    async def test_plain_text_is_unchanged(self):
        result = await remove_html_from_string("This is a plain text.")
        self.assertEqual(result, "This is a plain text.")

    async def test_invalid_input_raises_value_error(self):
        with self.assertRaises(ValueError):
            await remove_html_from_string(None, preserve_important_tags=True)  # type: ignore[arg-type]

    async def test_removes_all_html_when_preservation_disabled(self):
        result = await remove_html_from_string(
            "<div><p>This is a <b>bold</b> text.</p></div>",
            preserve_important_tags=False,
        )
        self.assertEqual(result, "This is a bold text.")

    async def test_preserves_selected_tags_when_preservation_enabled(self):
        result = await remove_html_from_string(
            '<div class="container"><p id="text">Hello <b>world</b>!</p></div>',
            preserve_important_tags=True,
        )
        self.assertEqual(result, "Hello <b>world</b>!")

    async def test_removes_all_attributes_when_preservation_disabled(self):
        result = await remove_html_from_string(
            '<div class="container"><p id="text">Hello <b>world</b>!</p></div>',
            preserve_important_tags=False,
        )
        self.assertEqual(result, "Hello world!")

    async def test_preserves_b_tag_with_inline_style(self):
        result = await remove_html_from_string(
            '<b style="font-weight: bold;">Bold text</b> with normal text.',
            preserve_important_tags=True,
        )
        self.assertEqual(result, '<b style="font-weight: bold;">Bold text</b> with normal text.')

    async def test_preserves_unknown_tags_as_passthrough(self):
        result = await remove_html_from_string(
            "<div><p>This is a <unknown>tag</unknown>.</p></div>",
            preserve_important_tags=True,
        )
        self.assertEqual(result, "This is a <unknown>tag</unknown>.")

    async def test_uppercased_html_tags_are_removed(self):
        result = await remove_html_from_string(
            "<DIV><p>This is <b>weird</b><p></DIV>",
            preserve_important_tags=False,
        )
        self.assertEqual(result, "This is weird")

    async def test_preserves_self_closing_br_tags(self):
        result = await remove_html_from_string(
            "This is a line break.<br/>It is followed by another line.",
            preserve_important_tags=True,
        )
        self.assertEqual(result, "This is a line break.<br/>It is followed by another line.")

    async def test_removes_self_closing_br_tags_when_preservation_disabled(self):
        result = await remove_html_from_string(
            "This is a line break.<br/>It is followed by another line.",
            preserve_important_tags=False,
        )
        self.assertEqual(result, "This is a line break.It is followed by another line.")


if __name__ == "__main__":
    unittest.main()
