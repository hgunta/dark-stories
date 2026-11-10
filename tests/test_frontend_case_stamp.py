"""Contract tests for the pixel case-stamp facelift (no JS/browser/network dependencies)."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import pytest

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


def test_no_per_case_images_and_approved_fonts_and_magnifier():
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    parser = Tags()
    parser.feed(html)
    assert not any(tag == "img" for tag, _ in parser.tags)
    assert "fonts.googleapis.com/css2?family=Inter" in html
    assert "Press+Start+2P" in html
    assert '"Press Start 2P"' in css
    assert '"Inter"' in css
    assert "background-image:url" not in css.replace(" ", "").lower()
    assert "case-stamp" in html
    assert "<svg" in html and "Pixel magnifying glass" in html
    assert "shape-rendering=\"crispEdges\"" in html
    assert "M31 31h5v5h-5z" in html
    assert "balance" not in html.lower() and "scales" not in html.lower()
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
    assert re.search(r"grid-template-columns:\\s*1fr", css)
    assert re.search(r"\\.composer\\s*\\{\\s*flex-basis:\\s*100%", css)


def test_browser_script_parses_as_valid_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable in this test environment")
    html = HTML.read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
    assert len(scripts) == 1
    checked = subprocess.run([node, "--check", "-"], input=scripts[0],
                             text=True, capture_output=True, timeout=10)
    assert checked.returncode == 0, checked.stderr


def test_case_file_skin_has_paper_surface_but_chat_uses_inter():
    css = CSS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    assert "--paper: #f1cfa4" in css
    assert "--wine: #661f32" in css
    assert ".featured-case" in css and "background: linear-gradient(145deg, #f5d5ae, #e9bb8c)" in css
    assert ".msg.user" in css and ".msg.bot" in css
    assert "font: 400 .96rem/1.65 var(--font-body)" in css
    assert "No daily login required." in html
    assert "https://fonts.gstatic.com" in html
