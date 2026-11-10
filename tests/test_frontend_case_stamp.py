"""Contract tests for the pixel case-stamp facelift (no JS/browser/network dependencies)."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "index.html"
CSS = ROOT / "frontend" / "case-stamp.css"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.tags = []
        self.links = []
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        self.tags.append((tag, attr))
        if "id" in attr:
            self.ids.append(attr["id"])
        if tag == "link":
            self.links.append(attr.get("href"))
        if tag == "button":
            self.buttons.append(attr)


def test_all_expected_game_actions_remain_addressable():
    text = HTML.read_text(encoding="utf-8")
    parser = Tags()
    parser.feed(text)
    assert len(parser.ids) == len(set(parser.ids)), "Duplicate DOM IDs break listeners"
    assert {
        "landing-view", "game-view", "library-section", "case-grid",
        "mystery-select", "start-game", "random-premise",
        "premise", "chat", "input", "send", "hint", "reveal",
        "private-guess-form", "private-guess-input", "private-guess-submit",
        "feedback-form", "feedback-panel", "share", "case-share",
        "room-share", "current-room", "join-room", "join-code",
        "public-feed", "public-events",
    }.issubset(set(parser.ids))
    assert "/static/case-stamp.css" in parser.links


def test_no_per_case_image_assets_or_external_typefaces():
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    parser = Tags()
    parser.feed(html)
    assert not any(tag == "img" for tag, _ in parser.tags)
    assert "https://fonts." not in html + css
    assert "background-image:url" not in css.replace(" ", "").lower()
    assert "case-stamp" in html
    assert "<svg" in html and "circle cx=" in html
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css


def test_library_uses_safe_text_rendering_and_existing_backend_contracts():
    html = HTML.read_text(encoding="utf-8")
    assert "card.append(n,title,meta)" in html
    assert "title.textContent = item.title" in html
    assert "el('case-grid').innerHTML" not in html
    for endpoint in (
        "/api/mysteries", "/api/create_room", "/api/join/",
        "/api/message", "/api/private_guess", "/api/feedback",
        "/api/hint", "/api/reveal", "/api/room_state/",
    ):
        assert endpoint in html
    assert "else showView('landing')" in html
    assert "await joinRoom(invitedCode)" in html
    assert "await createRoom(caseId)" in html


def test_game_chat_and_case_library_are_mobile_responsive():
    css = CSS.read_text(encoding="utf-8")
    for marker in (".msg.user", ".msg.bot", ".case-grid", ".case-tile",
                   ".composer", ".send-in", "@media(max-width:650px)"):
        assert marker in css
    assert "grid-template-columns:1fr" in css
    assert ".composer{flex-basis:100%}" in css
