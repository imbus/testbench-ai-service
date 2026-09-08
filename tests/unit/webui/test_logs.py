import logging
from pathlib import Path

from testbench_ai_service.models.logging import FileLoggerConfig
from testbench_ai_service.webui.logs import parse_log_line, tail_lines

SAMPLE = (
    "2026-09-08 10:11:50,123 -     INFO - auth - JWT validated for a.mueller\n"
    "2026-09-08 10:12:03,000 -  WARNING - llm.openai - request timed out\n"
)


def test_tail_returns_last_n_lines(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    assert tail_lines(log, 5) == [f"line {i}" for i in range(95, 100)]


def test_tail_handles_fewer_lines_than_requested(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("only one", encoding="utf-8")
    assert tail_lines(log, 50) == ["only one"]


def test_tail_of_missing_file_is_empty(tmp_path: Path):
    assert tail_lines(tmp_path / "absent.log", 10) == []


def test_tail_of_empty_file_is_empty(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("", encoding="utf-8")
    assert tail_lines(log, 10) == []


def test_parses_the_default_file_format():
    line = parse_log_line(SAMPLE.splitlines()[0])
    assert line.level == "INFO"
    assert line.source == "auth"
    assert line.message == "JWT validated for a.mueller"
    assert line.timestamp == "2026-09-08 10:11:50"


def test_unparseable_line_is_returned_raw():
    line = parse_log_line("  Traceback (most recent call last):")
    assert line.level is None
    assert line.raw == "  Traceback (most recent call last):"
    assert line.message == "  Traceback (most recent call last):"


def test_parses_a_genuinely_formatted_line():
    """Format a real ``LogRecord`` through the service's actual file
    ``log_format`` (``%(levelname)8s`` space-pads the level, and ``asctime``
    carries a ``,milliseconds`` suffix) rather than trusting only a
    hand-written sample -- a regex that happens to match the brief's example
    but not genuine padding would slip past a test built from a fabricated
    string.
    """
    formatter = logging.Formatter(FileLoggerConfig().log_format)
    record = logging.LogRecord(
        name="webui.logs",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)

    line = parse_log_line(formatted)

    assert line.level == "ERROR"
    assert line.source == "webui.logs"
    assert line.message == "boom"


def test_endpoint_requires_a_session(client):
    assert client.get("/admin/api/logs").status_code == 401


def test_endpoint_returns_newest_first(client, login, tmp_path, monkeypatch):
    log = tmp_path / "svc.log"
    log.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client.app.state.config.logging.file.file_name = "svc.log"
    login()
    body = client.get("/admin/api/logs?limit=10").json()
    assert body[0]["level"] == "WARNING"
    assert body[1]["level"] == "INFO"


def test_limit_is_bounded(client, login):
    login()
    assert client.get("/admin/api/logs?limit=100000").status_code == 422
