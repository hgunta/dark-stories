"""Loopback and browser-origin boundaries on a separate development app."""

from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from backend.analytics_dashboard import create_dashboard
from backend.analytics_sample import generate_sample


@pytest.fixture
def dashboard(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    generate_sample(path)
    return create_dashboard(path)


@pytest.fixture
def browser(dashboard):
    with TestClient(dashboard, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)) as client:
        yield client


def test_local_dashboard_and_assets_render(browser):
    response = browser.get("/")
    assert response.status_code == 200
    assert "LOCAL ONLY" in response.text
    assert "Mystery samples" in response.text
    assert '<script src="/dashboard.js" defer>' in response.text
    assert browser.get("/dashboard.js").status_code == 200
    assert "textContent" in browser.get("/dashboard.js").text
    assert browser.get("/dashboard.css").status_code == 200
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_aggregate_api_is_labeled_and_has_no_raw_events(browser):
    result = browser.get("/api/report")
    assert result.status_code == 200
    assert result.json()["dataset_label"] == "Synthetic sample data"
    assert result.json()["summary"]["game_starts"] == 5
    # Coverage labels such as conflicting_event_ids are aggregate counts, not IDs.
    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()
    assert not {"event_id", "attempt_id", "game_session_id", "browser_visit_id", "properties"} & keys(result.json())


@pytest.mark.parametrize("peer", ["203.0.113.1", "10.0.0.2", "testclient"])
def test_non_loopback_peers_cannot_spoof_forwarded_headers(dashboard, peer):
    with TestClient(dashboard, base_url="http://127.0.0.1:8765", client=(peer, 50000)) as client:
        response = client.get("/api/report", headers={"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost:8765"})
        assert response.status_code == 403


@pytest.mark.parametrize("headers", [
    {"Host": "attacker.example:8765"}, {"Host": "attacker.example@localhost:8765"},
    {"Origin": "https://attacker.example"}, {"Origin": "null"},
    {"Origin": "http://127.0.0.1:9000"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
])
def test_dns_rebinding_and_cross_origin_browser_reads_denied(browser, headers):
    assert browser.get("/api/report", headers=headers).status_code == 403


def test_same_origin_allowed_but_no_write_or_docs_endpoints(browser):
    assert browser.get("/api/report", headers={"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert browser.post("/api/report").status_code == 405
    assert browser.get("/docs").status_code == 404
    assert browser.get("/openapi.json").status_code == 404
    assert browser.get("/api/create_room").status_code == 404


def test_bad_database_error_is_generic_without_paths(tmp_path):
    path = tmp_path / "private-filename.sqlite3"
    path.write_bytes(b"not a sqlite database")
    app = create_dashboard(path)
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/report")
        assert response.status_code == 503
        assert str(path) not in response.text


@pytest.mark.parametrize("changes", [{"environment": "production"}, {"environment": "staging"}, {"mode": "all"}, {"port": 0}])
def test_dashboard_rejects_production_or_invalid_configuration(tmp_path, changes):
    path = tmp_path / "sample.sqlite3"
    generate_sample(path)
    with pytest.raises(ValueError):
        create_dashboard(path, **changes)


def test_cli_binds_loopback_and_disables_proxy_trust(tmp_path, monkeypatch):
    from backend.analytics_dashboard import main

    path = tmp_path / "sample.sqlite3"
    generate_sample(path)
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    main(["--database", str(path)])
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["proxy_headers"] is False
    with pytest.raises(SystemExit):
        main(["--database", str(path), "--host", "0.0.0.0"])


def test_production_app_exposes_no_dashboard_or_report(client, isolated_app):
    assert isolated_app.analytics_recorder.enabled is False
    assert client.get("/api/report").status_code == 404
    assert "Local analytics" not in client.get("/").text
    assert client.get("/dashboard.js").status_code == 404
    assert "/api/report" not in client.get("/openapi.json").json()["paths"]


def test_factory_never_creates_missing_database(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        create_dashboard(path)
    assert not path.exists()
