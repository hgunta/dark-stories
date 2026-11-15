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
    html = HTML.read_text(encoding="utf-8")
    parser = Tags()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids)), "Duplicate DOM IDs break listeners"
    assert {
        "landing-view", "game-view", "library-section", "case-grid",
        "mystery-select", "start-game", "browse-cases", "featured-premise",
        "premise", "chat", "input", "send", "hint", "reveal",
        "case-brief", "case-opening-question", "feedback-note", "feedback-followup",
        "feedback-form", "feedback-panel", "rating-stars", "share", "case-share",
        "case-privacy", "share-sheet-overlay", "case-finished", "finished-cases",
    }.issubset(set(parser.ids))
    assert 'id="case-menu"' not in html
    assert 'id="random-premise"' not in html
    assert any(link and link.startswith("/static/case-stamp.css") for link in parser.links)

def test_no_per_case_images_and_approved_fonts_and_magnifier():
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    parser = Tags()
    parser.feed(html)
    assert not any(tag == "img" for tag, _ in parser.tags)
    assert "fonts.googleapis.com/css2?family=Inter" in html
    assert "Press+Start+2P" in html
    assert '"Press Start 2P"' in css
    assert '--font-body: var(--font-pixel)' in css
    assert 'font-synthesis:none' in css
    assert 'font-stretch:normal' in css
    # The only picture is the approved logo sprite, never per-mystery artwork.
    assert 'class="case-stamp pixel-magnifier-reference"' in html
    assert css.replace(" ","").count("background-image:url(") == 1
    assert 'background-image:url("data:image/png;base64,' in css
    assert 'class="pixel-folder"' not in html
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
        "/api/message", "/api/feedback",
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
    compact = "".join(css.split())
    assert "grid-template-columns:1fr" in compact
    assert ".composer{flex-basis:100%}" in compact


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


def test_case_file_skin_has_paper_surface_and_chat_uses_pixel_type():
    css = CSS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    assert "--paper: #f1cfa4" in css
    assert "--wine: #661f32" in css
    assert "#landing-view .featured-case" in css
    assert "border:3px solid var(--mock-outline)" in css
    assert "background:#111119" in css
    assert ".msg.user" in css and ".msg.bot" in css
    assert "#game-view .chat .msg" in css
    assert "font:400 11px/1.92 var(--font-pixel)" in css
    assert "font:400 11px/2.05 var(--font-pixel)" in css
    assert "Inter:wght" not in html
    assert "No daily login required." not in html
    assert "https://fonts.gstatic.com" in html

def test_minimal_typographic_hierarchy_and_no_redundant_chrome():
    css = CSS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    assert "--size-title: 20px" in css
    assert "--size-body: 16px" in css
    assert "--size-small: 13px" in css
    # Approved design uses one pixel font for all UI outside the conversation.
    assert "#landing-view button" in css
    assert "#game-view button" in css
    assert "font-family:var(--font-pixel)" in css
    assert "#game-view .chat .msg" in css and "font-family:var(--font-pixel)" in css
    assert "#case-grid.case-file-stack" in css
    assert 'class="brand-small"' not in html
    assert 'class="ui-eyebrow"' not in html
    assert "No spoilers</span>" not in html
    assert "No daily login required." not in html

