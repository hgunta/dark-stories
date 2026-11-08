"""DS-010A: frontend retries do not leak internal errors or silently lose user input."""
from pathlib import Path


def test_frontend_has_safe_retry_paths():
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "function showRequestError(error, action)" in html
    assert "the service is temporarily unavailable. Please try again." in html
    assert "if (!el('input').value.trim()) el('input').value = text;" in html
    assert "if (ROOM_ID !== activeRoom) return;" in html
    assert "showRequestError(error, 'start the game');" in html
    assert "showRequestError(error, 'send that question');" in html
    assert "showRequestError(error, 'get a hint');" in html
    assert "showRequestError(error, 'reveal the solution');" in html
    # Keep the chat visible until a new room is actually created.
    assert html.index("document.getElementById('chat').innerHTML = \"\";") > html.index("data = await fetchJSON(API('/api/create_room')")


def test_frontend_does_not_display_exception_text():
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    start = html.index("function showRequestError(error, action)")
    end = html.index("async function createRoom", start)
    function = html[start:end]
    assert "error.stack" not in function
    assert "error.toString()" not in function
    assert "addMsg('bot', unavailable" in function
