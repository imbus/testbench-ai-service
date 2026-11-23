from testbench_ai_service.webui.diff import file_diff


def test_identical_text_yields_no_diff():
    assert file_diff("config.toml", "a = 1\n", "a = 1\n") is None


def test_a_changed_line_is_reported_as_one_added_and_one_removed():
    result = file_diff("config.toml", "port = 8010\n", "port = 9999\n")

    assert result is not None
    assert result.path == "config.toml"
    assert result.added == 1
    assert result.removed == 1
    assert "-port = 8010" in result.diff
    assert "+port = 9999" in result.diff


def test_an_added_line_is_reported_as_added_only():
    result = file_diff("config.toml", "a = 1\n", "a = 1\nb = 2\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 0)
    assert "+b = 2" in result.diff


def test_a_removed_line_is_reported_as_removed_only():
    result = file_diff("config.toml", "a = 1\nb = 2\n", "a = 1\n")

    assert result is not None
    assert (result.added, result.removed) == (0, 1)
    assert "-b = 2" in result.diff


def test_a_new_file_diffs_against_empty_text():
    result = file_diff("config.toml", "", "port = 8010\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 0)


def test_the_diff_carries_the_path_in_its_headers():
    result = file_diff("config.toml", "a = 1\n", "a = 2\n")

    assert result is not None
    assert result.diff.startswith("--- config.toml")
    assert "+++ config.toml" in result.diff


def test_the_file_header_markers_are_not_counted_as_changes():
    """'--- a' and '+++ b' start with the same characters as real changes."""
    result = file_diff("config.toml", "a = 1\n", "a = 2\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 1)


def test_context_lines_are_included_around_a_change():
    current = "".join(f"key_{index} = {index}\n" for index in range(20))
    proposed = current.replace("key_10 = 10", "key_10 = 999")

    result = file_diff("config.toml", current, proposed)

    assert result is not None
    assert "key_8 = 8" in result.diff
    assert "key_12 = 12" in result.diff
    # Not the whole file: a 20-line file with one change must not diff as 20.
    assert "key_0 = 0" not in result.diff


def test_utf8_content_diffs_without_mangling():
    result = file_diff("config.toml", 'note = "a"\n', 'note = "Pruefstand"\n')

    assert result is not None
    assert "Pruefstand" in result.diff


def test_a_trailing_newline_difference_is_a_real_diff():
    result = file_diff("config.toml", "a = 1", "a = 1\n")

    assert result is not None
