from unittest.mock import MagicMock

from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)

from testbench_ai_service.utils.testbench_helpers import (
    get_keyword_calls_for_test_case,
    parameter_combinations_as_str,
)
from testbench_ai_service.utils.testbench_helpers import (
    test_case_set_as_str as _tcs_as_str,
)


def _make_call(
    name: str,
    key: str = "k1",
    keyword_type=KeywordType.Textual,
    call_type=KeywordCallType.Flow,
    parent_id=None,
    call_parameters=None,
):
    call = MagicMock()
    call.spec = MagicMock()
    call.spec.name = name
    call.spec.key = key
    call.spec.keywordType = keyword_type
    call.spec.callType = call_type
    call.spec.callParameters = call_parameters or []
    call.parentID = parent_id
    return call


def _make_param(name: str, value: str | None = None, param_value=None):
    p = MagicMock()
    p.name = name
    p.value = value
    p.parameterValue = param_value
    return p


def _make_tc(sequence: list):
    tc = MagicMock()
    tc.testSequence = sequence
    tc.uniqueID = "tc1"
    tc.parameters = []
    return tc


def _make_tcs(name: str, test_cases: dict):
    tcs = MagicMock()
    tcs.details = MagicMock()
    tcs.details.name = name
    tcs.test_cases = test_cases
    return tcs


def _make_param_tc(unique_id: str, params: list):
    tc = MagicMock()
    tc.uniqueID = unique_id
    tc.parameters = params
    return tc


def _make_param_combo_tcs(test_cases: dict):
    tcs = MagicMock()
    tcs.test_cases = test_cases
    return tcs


class TestGetKeywordCallsForTestCase:
    """Tests for ``get_keyword_calls_for_test_case``."""

    def test_returns_all_top_level_calls(self):
        calls = [_make_call("A"), _make_call("B")]
        tc = _make_tc(calls)
        assert get_keyword_calls_for_test_case(tc) == calls

    def test_excludes_child_calls(self):
        parent = _make_call("Parent", parent_id=None)
        child = _make_call("Child", parent_id="p1")
        tc = _make_tc([parent, child])
        assert get_keyword_calls_for_test_case(tc) == [parent]

    def test_empty_sequence_returns_empty_list(self):
        assert get_keyword_calls_for_test_case(_make_tc([])) == []

    def test_preserves_order(self):
        calls = [_make_call("Z"), _make_call("A"), _make_call("M")]
        tc = _make_tc(calls)
        assert get_keyword_calls_for_test_case(tc) == calls


class TestTestCaseSetAsStr:
    """Tests for ``test_case_set_as_str``."""

    def test_first_line_is_test_case_set_name(self):
        tc = _make_tc([_make_call("Step")])
        tcs = _make_tcs("MySet", {"tc1": tc})
        assert _tcs_as_str(tcs).startswith("MySet")

    def test_step_name_appears_in_output(self):
        tc = _make_tc([_make_call("Do Something")])
        tcs = _make_tcs("S", {"tc1": tc})
        assert "Do Something" in _tcs_as_str(tcs)

    def test_textual_step_has_no_step_type_annotation(self):
        tc = _make_tc([_make_call("Text Step", keyword_type=KeywordType.Textual)])
        tcs = _make_tcs("S", {"tc1": tc})
        assert "step_type:" not in _tcs_as_str(tcs)

    def test_atomic_flow_step_annotated(self):
        tc = _make_tc(
            [_make_call("Flow", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Flow)]
        )
        tcs = _make_tcs("S", {"tc1": tc})
        assert "step_type:flow" in _tcs_as_str(tcs)

    def test_atomic_check_step_annotated(self):
        tc = _make_tc(
            [_make_call("Check", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Check)]
        )
        tcs = _make_tcs("S", {"tc1": tc})
        assert "step_type:check" in _tcs_as_str(tcs)

    def test_uses_first_test_case_only(self):
        tc1 = _make_tc([_make_call("First Step")])
        tc2 = _make_tc([_make_call("Second Step")])
        tcs = _make_tcs("S", {"a": tc1, "b": tc2})
        result = _tcs_as_str(tcs)
        assert "First Step" in result
        assert "Second Step" not in result

    def test_empty_test_sequence_returns_name_only(self):
        tc = _make_tc([])
        tcs = _make_tcs("OnlyName", {"tc1": tc})
        assert _tcs_as_str(tcs) == "OnlyName"

    def test_literal_param_rendered_with_repr(self):
        param = _make_param("Speed", value="100", param_value=None)
        step = _make_call("Drive", call_parameters=[param])
        tc = _make_tc([step])
        tcs = _make_tcs("S", {"tc1": tc})
        assert "Speed='100'" in _tcs_as_str(tcs)

    def test_abstract_param_rendered_with_dollar_braces(self):
        pv = MagicMock()
        pv.name = "SpeedParam"
        param = _make_param("Speed", param_value=pv)
        step = _make_call("Drive", call_parameters=[param])
        tc = _make_tc([step])
        tcs = _make_tcs("S", {"tc1": tc})
        assert "Speed=${SpeedParam}" in _tcs_as_str(tcs)

    def test_consecutive_duplicate_steps_collapsed(self):
        """Two consecutive calls with the same spec.key collapse into one step."""
        param1 = _make_param("Val", value="a", param_value=None)
        param2 = _make_param("Val", value="b", param_value=None)
        call1 = _make_call("Do", key="same", call_parameters=[param1])
        call2 = _make_call("Do", key="same", call_parameters=[param2])
        tc = _make_tc([call1, call2])
        tcs = _make_tcs("S", {"tc1": tc})
        result = _tcs_as_str(tcs)
        assert result.count("Do") == 1

    def test_non_consecutive_duplicate_steps_not_collapsed(self):
        """Two non-consecutive calls with the same spec.key remain separate."""
        call1 = _make_call("Do", key="same")
        call2 = _make_call("Other", key="other")
        call3 = _make_call("Do", key="same")
        tc = _make_tc([call1, call2, call3])
        tcs = _make_tcs("S", {"tc1": tc})
        result = _tcs_as_str(tcs)
        assert result.count("Do") == 2

    def test_each_step_on_its_own_line(self):
        tc = _make_tc([_make_call("Step A", key="k1"), _make_call("Step B", key="k2")])
        tcs = _make_tcs("S", {"tc1": tc})
        lines = _tcs_as_str(tcs).splitlines()
        assert any("Step A" in ln for ln in lines)
        assert any("Step B" in ln for ln in lines)
        assert lines[0] == "S"


class TestParameterCombinationsAsStr:
    """Tests for ``parameter_combinations_as_str``."""

    def test_header_contains_all_param_names(self):
        p = _make_param("Color", value="Red")
        tc = _make_param_tc("TC1", [p])
        tcs = _make_param_combo_tcs({"tc1": tc})
        result = parameter_combinations_as_str(tcs)
        assert "Color" in result

    def test_row_contains_tc_unique_id(self):
        p = _make_param("X", value="1")
        tc = _make_param_tc("MY-TC", [p])
        tcs = _make_param_combo_tcs({"tc1": tc})
        assert "MY-TC" in parameter_combinations_as_str(tcs)

    def test_empty_test_cases_returns_header_and_separator_only(self):
        tcs = _make_param_combo_tcs({})
        result = parameter_combinations_as_str(tcs)
        lines = result.splitlines()
        # Only header and separator when no rows
        assert len(lines) == 2

    def test_none_param_value_becomes_empty_string(self):
        p = _make_param("X", value=None)
        tc = _make_param_tc("TC1", [p])
        tcs = _make_param_combo_tcs({"tc1": tc})
        result = parameter_combinations_as_str(tcs)
        # "X" column present, value cell empty (just pipe separators)
        assert "X" in result
