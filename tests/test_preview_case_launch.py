"""Regression: preview chat-first layout must not crash when opening a case."""
from pathlib import Path

def test_missing_legacy_room_nodes_do_not_block_case_launch():
    html = (Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    # The preview intentionally does not render the hidden legacy room panel.
    assert 'id="current-room"' not in html
    assert 'id="room-share"' not in html
    assert 'id="public-events"' not in html
    # Case creation calls setRoomDisplay; every optional node must be guarded.
    assert "if (roomLabel) roomLabel.textContent" in html
    assert "if (roomShare) roomShare.disabled" in html
    assert "el('public-events')?.replaceChildren()" in html
    assert "if (!target) return;" in html
