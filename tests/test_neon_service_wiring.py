"""Neon integration contract without making network calls."""
from pathlib import Path

def test_integration_status_does_not_expose_secrets(client, isolated_app, monkeypatch):
    monkeypatch.setattr(isolated_app, "NEON_GATEWAY_CONFIGURED", True)
    monkeypatch.setattr(isolated_app, "MODERATOR_PROVIDER", "openai")
    monkeypatch.setenv("NEON_REALTIME_URL", "https://example-neon-realtime.invalid/")
    monkeypatch.setenv("NEON_REALTIME_SECRET", "TEST_NOT_REAL_SECRET")
    data=client.get("/api/neon/status")
    assert data.status_code == 200
    body=data.json()
    assert body["ai_gateway_configured"] is True
    assert body["ai_gateway_active_for_moderator"] is False
    assert body["realtime_configured"] is True
    assert body["realtime_live_subscription_verified"] is False
    assert "TEST_NOT_REAL_SECRET" not in data.text
    assert "example-neon-realtime" not in data.text

def test_gateway_provider_is_explicitly_opt_in():
    source=(Path(__file__).resolve().parents[1]/"backend"/"app.py").read_text()
    assert 'os.getenv("DARK_STORIES_MODERATOR_PROVIDER", "openai")' in source
    assert 'base_url=_gateway_host + "/v1"' in source
    assert 'OpenAI(api_key=API_KEY)' in source
    assert 'NEON_AI_GATEWAY_TOKEN' in source

def test_neon_iac_declaration():
    root=Path(__file__).resolve().parents[1]
    cfg=(root/"neon.ts").read_text()
    assert 'aiGateway: true' in cfg
    assert 'realtime: true' in cfg
    assert 'DATABASE_URL=' not in cfg
