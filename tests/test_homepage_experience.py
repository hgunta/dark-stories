"""Homepage UX contract and all-beta-case voluntary transcript consent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_visible_game_brand_and_crisp_folder():
    html = (ROOT / "frontend/index.html").read_text()
    assert "<title>Crack the Case — Solve a Mystery</title>" in html
    assert ">CRACK THE CASE<" in html
    assert 'aria-label="Crack the Case home"' in html
    folder = html.split('<svg class="pixel-folder"', 1)[1].split("</svg>",1)[0]
    assert 'viewBox="0 0 96 72"' in folder
    assert 'shape-rendering="crispEdges"' in folder
    assert 'raised tab' in folder
    assert 'D6BFA2' not in folder  # old document-and-filing-cabinet icon

def test_homepage_has_no_beta_disclaimer_but_preserves_game_consent():
    html = (ROOT / "frontend/index.html").read_text()
    hero = html.split('<div class="hero">', 1)[1].split('</div>', 1)[0]
    assert "Every story has a secret." in hero
    assert "Ask yes-or-no questions" in hero
    assert "Public beta" not in hero
    assert 'class="beta-note"' not in hero
    assert 'id="playtest-opt-in"' in html
    assert "Share future chat to improve the moderator" in html

def test_featured_case_rotates_and_start_matches_selection():
    html = (ROOT / "frontend/index.html").read_text()
    assert "sessionStorage.getItem('crack-the-case-last-featured')" in html
    assert "items.filter(item => item.id !== prior)" in html
    assert "Math.floor(Math.random() * eligible.length)" in html
    assert "el('mystery-select').value = featured.id" in html
    assert "el('featured-title').textContent = featured.title" in html
    assert "el('start-game')?.addEventListener('click', () => createRoom(el('mystery-select')?.value || CURRENT_MYSTERY))" in html

def test_opt_in_below_chat_is_one_step_and_never_preselected():
    html = (ROOT / "frontend/index.html").read_text()
    assert html.count('id="playtest-opt-in"') == 1
    assert html.index('id="chat"') < html.index('id="playtest-opt-in-panel"')
    assert html.index('class="controls"') < html.index('id="playtest-opt-in-panel"')
    assert 'id="playtest-sharing-details"' not in html
    assert 'id="playtest-receipt"' not in html
    assert "Share future chat to improve the moderator" in html
    assert "el('playtest-opt-in-panel').hidden" in html
    assert "possible AI training" in html
    assert 'checked id="playtest-opt-in"' not in html

def test_original_beta_room_can_opt_in_when_storage_is_configured(client, isolated_app, monkeypatch):
    class FakeStore:
        def initialize(self): pass
        def start(self, case_id, revision):
            assert case_id == "ms-001"
            return "fake-playtest-session"
        def consent(self, session_id):
            assert session_id == "fake-playtest-session"
            return "fake-deletion-receipt"
    monkeypatch.setattr(isolated_app, "playtest_store", FakeStore())
    monkeypatch.setenv("DARK_STORIES_BETA_COLLECT_ALL", "true")
    status = client.get("/api/playtest/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert status.json()["all_cases"] is True
    room = client.post("/api/create_room", json={"mystery_id":"ms-001"})
    assert room.status_code == 200
    data = room.json()
    assert data["playtest_consent_key"]
    assert isolated_app.ROOMS[data["room_id"]]["playtest_consented"] is False
    consent = client.post("/api/playtest/consent", json={
        "room_id":data["room_id"], "consent_key":data["playtest_consent_key"]
    })
    assert consent.status_code == 200
    assert consent.json()["enabled"] is True
    assert consent.json()["deletion_token"] == "fake-deletion-receipt"

def test_research_store_accepts_only_published_originals_and_experiment_format():
    from backend.playtest_store import CASE_ID
    assert CASE_ID.fullmatch("ms-001")
    assert CASE_ID.fullmatch("ms-002")
    assert CASE_ID.fullmatch("ms-003")
    assert CASE_ID.fullmatch("ex-001")
    assert not CASE_ID.fullmatch("ms-004")
    assert not CASE_ID.fullmatch("ms-999")
