"""Public beta release contract: exactly five cases, subtle voluntary consent,
and an in-conversation rating card. Source controls are explicitly enforced.
"""
from pathlib import Path

PUBLIC_IDS={"ms-001","ms-002","ms-003"}
EXPERIMENTAL_IDS={"ex-001","ex-002"}

def test_beta_public_catalogs_and_starts(client):
    ordinary=client.get("/api/mysteries")
    experimental=client.get("/api/experimental_mysteries")
    assert ordinary.status_code == 200
    assert experimental.status_code == 200
    assert {m["id"] for m in ordinary.json()} == PUBLIC_IDS
    assert {m["id"] for m in experimental.json()} == EXPERIMENTAL_IDS
    for mid in sorted(PUBLIC_IDS|EXPERIMENTAL_IDS):
        response=client.post("/api/create_room",json={"mystery_id":mid})
        assert response.status_code==200, mid
    for mid in ("ms-004","ms-009","ms-012","missing"):
        response=client.post("/api/create_room",json={"mystery_id":mid})
        assert response.status_code==404
        assert response.json()=={"detail":"Mystery not found"}

def test_opt_in_is_optional_compact_and_never_prechecked():
    html=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert 'type="checkbox" id="playtest-opt-in"' in html
    assert 'id="playtest-sharing-details"' not in html
    assert "possible AI training" in html
    assert "Share future chat to improve the moderator" in html
    assert html.index('id="chat"') < html.index('id="playtest-opt-in-panel"')
    assert "el('playtest-opt-in-panel').hidden=true;" in html
    assert "Deletion receipt copied to clipboard." in html
    assert "window.prompt('Chat sharing enabled." in html
    assert "checked id=\"playtest-opt-in\"" not in html

def test_feedback_is_moved_into_chat_on_all_terminal_paths():
    html=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert "function showFeedbackInChat()" in html
    assert "el('chat').appendChild(panel)" in html
    assert "function resetFeedbackForNewRoom()" in html
    assert "el('feedback-parking').appendChild(panel)" in html
    assert 'How was this case?' in html
    # Single-chat solve and reveal both show the same feedback card.
    assert html.count("showFeedbackInChat();")>=2
    assert "Rate it below" not in html
