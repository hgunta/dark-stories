"""Offline library review is self-contained and never served by FastAPI."""
import json
import re
import subprocess
import sys
from pathlib import Path

from backend.game import check_solution


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "build_mystery_review.py"
MYSTERIES = ROOT / "backend" / "mysteries"


def test_reviewer_generator_is_standalone_and_contains_all_cases(tmp_path):
    destination = tmp_path / "review.html"
    output = subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(destination)],
        capture_output=True, text=True, check=True
    )
    assert destination.exists()
    assert str(destination) in output.stdout
    html = destination.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="cases-json">(.*?)</script>',
        html, flags=re.S
    )
    assert match, "All review content must be embedded for offline use"
    cases = json.loads(match.group(1))
    disk_ids = {path.stem for path in MYSTERIES.glob("ms-*.json")}
    assert len(cases) == len(disk_ids)
    assert {c["mystery_id"] for c in cases} == disk_ids
    assert all(len(c["_review_fingerprint"]) == 16 for c in cases)
    for case in cases:
        assert case["solution_summary"]  # spoilers available to owner
        assert case["hints"]
        assert case["facts"]
    assert 'const STORE=' in html  # browser-local review progress
    assert "Export my reviews (JSON)" in html
    assert "Needs revision" in html
    assert "Approved for playtesting" in html
    assert 'Import previous reviews' in html
    assert 'revision-warning' in html
    assert 'const firstPending=CASES.findIndex(c=>needsReview(c))' in html
    assert "window.fetch(" not in html
    assert "<script src=" not in html


def test_reviewer_template_escapes_embedded_json_breakouts():
    template = (ROOT / "tools" / "mystery_review_template.html").read_text()
    assert template.count("__MYSTERY_DATA__") == 1
    builder = (ROOT / "tools" / "build_mystery_review.py").read_text()
    assert '.replace("<",' in builder
    assert "DEFAULT_OUTPUT = ROOT / \"mystery-review.html\"" in builder
    ignore = (ROOT / ".gitignore").read_text()
    assert "mystery-review.html" in ignore


def test_all_authored_solution_variants_work_in_offline_fallback():
    for source in sorted(MYSTERIES.glob("ms-*.json")):
        case = json.loads(source.read_text(encoding="utf-8"))
        for answer in case["acceptable_solutions"]:
            assert check_solution(answer, case["acceptable_solutions"]), source


def test_public_library_has_case_share_links_and_no_daily_gate():
    html = (ROOT / "frontend" / "index.html").read_text()
    assert "Explore the Mystery Library" in html
    assert 'id="case-share"' in html
    assert "async function shareLibraryCase()" in html
    assert "params.get('case')" in html
    assert "await createRoom(caseId)" in html
    assert "No daily login required." in html
    assert "/api/daily" not in html


def test_launcher_rebuilds_all_current_cases_without_web_open(tmp_path):
    launcher = ROOT / "tools" / "review_mysteries.py"
    assert (ROOT / "review-mysteries.command").exists()
    assert (ROOT / "review-mysteries.bat").exists()
    # Run from a different directory to ensure no cwd assumptions.
    command = subprocess.run(
        [sys.executable, str(launcher), "--no-open"],
        cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert "mysteries" in command.stdout
    generated = ROOT / "mystery-review.html"
    assert generated.exists()
    embedded = re.search(
        r'<script type="application/json" id="cases-json">(.*?)</script>',
        generated.read_text(encoding="utf-8"), flags=re.S
    )
    assert embedded
    assert len(json.loads(embedded.group(1))) == len(list(MYSTERIES.glob("ms-*.json")))
    generated.unlink()


def test_review_fingerprint_changes_when_case_content_changes(tmp_path, monkeypatch):
    from importlib.util import spec_from_file_location, module_from_spec
    name = "build_review_fingerprint_test"
    spec = spec_from_file_location(name, GENERATOR)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "cases"
    source.mkdir()
    original = json.loads((MYSTERIES / "ms-004.json").read_text())
    file = source / "ms-004.json"
    file.write_text(json.dumps(original))
    monkeypatch.setattr(module, "SOURCE", source)
    first = module.load_cases()[0]["_review_fingerprint"]
    original["hints"][0] += " A small revision."
    file.write_text(json.dumps(original))
    changed = module.load_cases()[0]["_review_fingerprint"]
    assert first != changed
    assert original["mystery_id"] == "ms-004"
