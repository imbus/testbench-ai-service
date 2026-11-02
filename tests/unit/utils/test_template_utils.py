import pytest
from jinja2.exceptions import SecurityError

from testbench_ai_service.utils.template_utils import render_template


def test_renders_a_write_back_template_with_its_values(tmp_path):
    template = tmp_path / "started.jinja"
    template.write_text(
        "<p>{{ current_time }}</p>{% if previous %}{{ previous }}{% endif %}", encoding="utf-8"
    )

    assert render_template(template, {"current_time": "12:00", "previous": "<b>x</b>"}) == (
        "<p>12:00</p><b>x</b>"
    )


@pytest.mark.parametrize(
    "escape",
    [
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ ''|attr('__class__') }}",
        "{{ '{0.__class__}'.format(1) }}",
    ],
)
def test_a_template_cannot_reach_python_internals(tmp_path, escape):
    # A write-back template is a file an operator can change, and in a setup
    # where templates_dir overlaps prompts_dir, one the web console can write.
    template = tmp_path / "evil.jinja"
    template.write_text(escape, encoding="utf-8")

    # The sandbox either refuses the access or hands back an undefined value
    # that renders empty and refuses any further access; unsandboxed, every
    # one of these prints a class.
    try:
        rendered = render_template(template, {})
    except SecurityError:
        return
    assert "class" not in rendered
