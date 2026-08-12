import pytest

from testbench_ai_service.utils.log_sanitizer import (
    MAX_BODY_CHARS,
    REDACTED,
    format_body,
    format_body_text,
    redact_secrets,
    truncate,
)


class TestRedactSecrets:
    @pytest.mark.parametrize(
        "key",
        ["password", "pwd", "api_key", "apiKey", "API-Key", "sessionToken", "Authorization"],
    )
    def test_secret_keys_are_redacted_whatever_their_spelling(self, key):
        assert redact_secrets({key: "hunter2"}) == {key: REDACTED}

    def test_non_secret_values_are_preserved(self):
        body = {"login": "tbadmin", "force": True, "count": 3}
        assert redact_secrets(body) == body

    def test_nested_dicts_are_redacted_at_depth(self):
        body = {"llm_config": {"model": "gpt-4o", "api_key": "sk-abc"}}
        assert redact_secrets(body) == {"llm_config": {"model": "gpt-4o", "api_key": REDACTED}}

    def test_lists_of_dicts_are_redacted_per_item(self):
        body = {"users": [{"login": "a", "password": "p1"}, {"login": "b", "password": "p2"}]}
        assert redact_secrets(body) == {
            "users": [{"login": "a", "password": REDACTED}, {"login": "b", "password": REDACTED}]
        }

    def test_secret_value_is_redacted_whatever_its_type(self):
        assert redact_secrets({"token": {"nested": "structure"}}) == {"token": REDACTED}

    @pytest.mark.parametrize("value", ["plain string", 42, None, True])
    def test_non_container_values_pass_through(self, value):
        assert redact_secrets(value) is value

    def test_input_is_not_mutated(self):
        body = {"password": "hunter2", "nested": {"token": "abc"}}
        redact_secrets(body)
        assert body == {"password": "hunter2", "nested": {"token": "abc"}}


class TestTruncate:
    def test_short_text_is_returned_unchanged(self):
        assert truncate("small") == "small"

    def test_text_at_the_limit_gets_no_marker(self):
        text = "x" * MAX_BODY_CHARS
        assert truncate(text) == text

    def test_longer_text_is_cut_and_marked_with_the_total(self):
        text = "x" * (MAX_BODY_CHARS + 31)
        result = truncate(text)
        assert result.startswith("x" * MAX_BODY_CHARS)
        assert result.endswith(f"... (truncated, {MAX_BODY_CHARS + 31} chars total)")


class TestFormatBody:
    def test_dict_is_serialized_as_json(self):
        assert format_body({"login": "tbadmin"}) == '{"login": "tbadmin"}'

    def test_non_ascii_is_kept_readable(self):
        assert format_body({"name": "Prüfung"}) == '{"name": "Prüfung"}'

    def test_unserializable_values_fall_back_to_their_string_form(self):
        assert format_body({"when": object()}).startswith('{"when": "<object object at')

    def test_long_body_is_truncated(self):
        result = format_body({"description": "x" * (MAX_BODY_CHARS + 100)})
        assert "... (truncated," in result

    def test_serialization_failure_yields_the_placeholder(self):
        body = {"outer": {}}
        body["outer"]["self"] = body  # circular reference
        assert format_body(body) == "<unserializable body>"


class TestFormatBodyText:
    def test_valid_json_is_redacted(self):
        assert format_body_text('{"password": "hunter2"}') == '{"password": "***"}'

    def test_invalid_json_is_returned_as_is(self):
        assert format_body_text("not json at all") == "not json at all"

    def test_invalid_json_is_still_truncated(self):
        result = format_body_text("y" * (MAX_BODY_CHARS + 5))
        assert "... (truncated," in result

    def test_empty_body_stays_empty(self):
        assert format_body_text("") == ""
