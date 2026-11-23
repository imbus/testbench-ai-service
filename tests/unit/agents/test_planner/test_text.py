from testbench_ai_service.agents.test_planner.text import build_embedding_text


def test_parts_in_fixed_order():
    text = build_embedding_text(
        "Login", "Checks the login.", ["TestStep: Open(url=x)"], {"user": "bob"}
    )

    assert text == "Login\nChecks the login.\nTestStep: Open(url=x)\nuser=bob"


def test_empty_parts_are_dropped():
    assert build_embedding_text("Login", "  ", [], {}) == "Login"


def test_parameters_are_sorted_by_name():
    text = build_embedding_text("S", "", [], {"b": "2", "a": "1"})

    assert text == "S\na=1\nb=2"


def test_same_input_gives_same_text():
    args = ("S", "D", ["x", "y"], {"p": "v"})

    assert build_embedding_text(*args) == build_embedding_text(*args)
