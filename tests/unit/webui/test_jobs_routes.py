import pytest
from sqlalchemy.exc import OperationalError


@pytest.fixture
def store(client):
    return client.app.state.job_store


def _create(store, job_id, user_key, agent_key="coverage_checker"):
    store.create(
        job_id,
        agent_key=agent_key,
        user_key=user_key,
        project_key="p",
        project_name="P",
        root_key=None,
        item_ids=["i1"],
        warnings=[],
    )


def _ids(response):
    assert response.status_code == 200
    return [j["job_id"] for j in response.json()]


def test_list_returns_only_own_jobs(client, login, store):
    login(roles=["Project User"])  # the session's user_key is "u-1"
    _create(store, "j1", "u-1")
    _create(store, "j2", "u-2")
    assert _ids(client.get("/admin/api/jobs")) == ["j1"]
    assert client.get("/admin/api/jobs/j2").status_code == 404


def test_admin_sees_only_own_jobs(client, login, store):
    login()
    _create(store, "mine", "u-1")
    _create(store, "foreign", "u-2")
    assert _ids(client.get("/admin/api/jobs")) == ["mine"]
    assert client.get("/admin/api/jobs/foreign").status_code == 404
    assert client.get("/admin/api/jobs/nope").status_code == 404


def test_filters_by_agent_and_status(client, login, store):
    login()
    _create(store, "j1", "u-1", agent_key="a")
    _create(store, "j2", "u-1", agent_key="b")
    store.finish("j2", "succeeded")
    assert _ids(client.get("/admin/api/jobs?agent=a")) == ["j1"]
    assert _ids(client.get("/admin/api/jobs?status=succeeded")) == ["j2"]
    assert _ids(client.get("/admin/api/jobs?status=failed")) == []
    assert client.get("/admin/api/jobs?status=bogus").status_code == 422


def test_limit_is_bounded(client, login, store):
    login()
    _create(store, "j1", "u-1")
    _create(store, "j2", "u-1")
    assert len(_ids(client.get("/admin/api/jobs?limit=1"))) == 1
    assert client.get("/admin/api/jobs?limit=0").status_code == 422
    assert client.get("/admin/api/jobs?limit=201").status_code == 422


def test_list_has_no_report_but_detail_includes_it(client, login, store):
    login()
    _create(store, "j1", "u-1")
    store.set_report("j1", "coverage_checker", {"a": 1})
    assert "report" not in client.get("/admin/api/jobs").json()[0]
    detail = client.get("/admin/api/jobs/j1")
    assert detail.status_code == 200
    assert detail.json()["report"] == {"a": 1}


def test_session_without_user_key_sees_nothing(client, login, store, tb_connection):
    # Review Focus 3: a job stored under "" must not leak to a keyless session.
    tb_connection.session.get.side_effect = ValueError("TB3")
    _create(store, "j1", "")
    login()
    assert client.get("/admin/api/jobs").json() == []
    assert client.get("/admin/api/jobs/j1").status_code == 404


def test_requires_session(client):
    assert client.get("/admin/api/jobs").status_code == 401
    assert client.get("/admin/api/jobs/j1").status_code == 401


def test_store_read_errors_are_503(client, login, store, monkeypatch):
    login()

    def broken(*args, **kwargs):
        raise OperationalError("select", {}, Exception("disk I/O error"))

    monkeypatch.setattr(store, "list_for_user", broken)
    monkeypatch.setattr(store, "get", broken)
    listed = client.get("/admin/api/jobs")
    read = client.get("/admin/api/jobs/j1")
    assert listed.status_code == 503
    assert read.status_code == 503
    assert "disk I/O" not in listed.text + read.text


def test_os_error_is_503(client, login, store, monkeypatch):
    login()

    def broken(*args, **kwargs):
        raise OSError("gone")

    monkeypatch.setattr(store, "list_for_user", broken)
    assert client.get("/admin/api/jobs").status_code == 503
