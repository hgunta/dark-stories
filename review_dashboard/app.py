"""Private, owner-only Crack the Case editorial review dashboard.

Each reviewer authenticates with a narrowly scoped GitHub fine-grained PAT.
The PAT is encrypted at rest in the browser's Secure, HttpOnly session cookie;
it is never written to the repository, server disk, logs or templates.
No backend credential or GitHub App registration is needed.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

ROOT = Path(__file__).resolve().parent
REPO = "hgunta/dark-stories-factory"
OWNER = "hgunta"
COOKIE_NAME = "ctc_review_session"
COOKIE_TTL = 60 * 60 * 24 * 7  # One week; token stays encrypted.
LOGIN_TTL = 60 * 15  # Short-lived, signed form CSRF challenge; no pre-login cookies.
log = logging.getLogger(__name__)
REVIEW_ACTIONS = {
    "advance": "APPROVED FOR HUMAN PLAYTEST — NOT FOR PUBLICATION",
    "revise": "CHANGES REQUESTED",
    "reject": "REJECTED",
}

app = FastAPI(title="Crack the Case — Private Review", docs_url=None, redoc_url=None,
              openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class GithubFailure(Exception):
    pass


def _cipher():
    key = os.getenv("REVIEW_SESSION_KEY", "")
    if not key:
        raise RuntimeError("REVIEW_SESSION_KEY must be configured")
    return Fernet(key.encode("ascii"))


def _session(request: Request):
    encrypted = request.cookies.get(COOKIE_NAME)
    if not encrypted:
        return None
    try:
        data = json.loads(_cipher().decrypt(encrypted.encode("ascii"),
                                           ttl=COOKIE_TTL).decode("utf-8"))
        if (not isinstance(data, dict) or data.get("login") != OWNER
                or not isinstance(data.get("token"), str)
                or not isinstance(data.get("csrf"), str)):
            return None
        return data
    except (InvalidToken, ValueError, TypeError, UnicodeError, RuntimeError):
        return None


def _login_challenge_ok(request: Request, value: str):
    # Stateless, authenticated form nonce. Modern privacy browsers may not
    # send Strict cookies after cross-site navigation (e.g. from ChatGPT).
    # Do not require a pre-login cookie; the nonce expires in 15 minutes.
    if not isinstance(value, str) or len(value) > 300:
        return False
    try:
        expected = _cipher().decrypt(value.encode("ascii"), ttl=LOGIN_TTL)
        return hmac.compare_digest(expected, b"ctc-login-v2")
    except (InvalidToken, ValueError, UnicodeError, RuntimeError):
        return False


def _login_form(request: Request, error=None):
    challenge = _cipher().encrypt(b"ctc-login-v2").decode("ascii")
    return _html(request, "login.html", error=error, login_csrf=challenge)


def _login_denied(request, reason, message):
    # Fixed reason codes ONLY: never log the token, incoming headers or address.
    log.warning("review_login_denied reason=%s", reason)
    return _login_form(request, error=message)


def _github(token: str, path: str, *, method="GET", payload=None):
    if not (path.startswith("/repos/" + REPO + "/") or
            path == "/repos/" + REPO or path == "/user"):
        raise GithubFailure("Invalid GitHub API path")
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.request(
                method, "https://api.github.com" + path,
                headers={"Authorization": "Bearer " + token,
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28",
                         "User-Agent": "crack-the-case-review"},
                json=payload)
        if response.status_code in (401, 403):
            raise GithubFailure("GitHub authorization failed. Reconnect using a token with access to the private factory.")
        if response.status_code == 404:
            raise GithubFailure("The private case or repository is unavailable with this token.")
        if response.status_code >= 400:
            raise GithubFailure("GitHub rejected the request (HTTP " + str(response.status_code) + ").")
        return response.json()
    except httpx.RequestError as exc:
        raise GithubFailure("Cannot contact GitHub. Please retry.") from exc
    except ValueError as exc:
        raise GithubFailure("Unexpected response from GitHub.") from exc


def _html(request, name, **kwargs):
    return templates.TemplateResponse(request=request, name=name, context=kwargs)


def _login_redirect():
    return RedirectResponse("/login", status_code=303)


def _failure(request, message, *, status_code=502):
    response = _html(request, "error.html", message=message)
    response.status_code = status_code
    return response


def _private_pr(pr):
    # Only same-repo branches created by our factory, never external forks.
    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != REPO:
        return False
    return head.get("ref", "").startswith(("factory-v", "factory/"))


def _pulls(token):
    result = _github(token, f"/repos/{REPO}/pulls?state=open&per_page=100")
    if not isinstance(result, list):
        raise GithubFailure("Malformed GitHub review queue")
    result = [p for p in result if _private_pr(p)]
    result.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    current = [p for p in result if p["head"]["ref"].startswith("factory-v24/")]
    historical = [p for p in result if p not in current]
    return current, historical


def _case(token, number):
    pr = _github(token, f"/repos/{REPO}/pulls/{number}")
    if not _private_pr(pr):
        raise GithubFailure("This pull request is not a private factory candidate.")
    head_sha = (pr.get("head") or {}).get("sha")
    if not re.fullmatch(r"[0-9a-f]{40}", str(head_sha)):
        raise GithubFailure("The candidate has an invalid revision")
    files = _github(token, f"/repos/{REPO}/pulls/{number}/files?per_page=100")
    if not isinstance(files, list):
        raise GithubFailure("Invalid candidate file listing")
    paths = [
        item.get("filename") for item in files
        if re.fullmatch(r"candidates/[A-Za-z0-9_-]+\.json",
                        str(item.get("filename", "")))
        and not item["filename"].endswith(".report.json")
    ]
    if len(paths) != 1:
        raise GithubFailure("Expected exactly one candidate JSON in the private PR.")
    base_path = paths[0][:-5]
    def read_json(path):
        result = _github(token, f"/repos/{REPO}/contents/{quote(path, safe='/')}?ref={head_sha}")
        if result.get("encoding") != "base64":
            raise GithubFailure("Unexpected GitHub file format")
        try:
            return json.loads(base64.b64decode(result["content"], validate=False))
        except (ValueError, KeyError, TypeError) as exc:
            raise GithubFailure("Malformed case assessment") from exc
    candidate = read_json(paths[0])
    report = read_json(base_path + ".report.json")
    if not isinstance(candidate, dict) or not isinstance(report, dict):
        raise GithubFailure("Invalid case or report JSON")
    if not isinstance(candidate.get("premise_public"), str):
        raise GithubFailure("Missing public premise")
    rounds = report.get("rounds") if isinstance(report.get("rounds"), list) else []
    latest = rounds[-1].get("review") if rounds and isinstance(rounds[-1], dict) else None
    latest = latest if isinstance(latest, dict) else {}
    creative = latest.get("creative_scores") or {}
    verdict = report.get("status", "unverified")
    actual = (report.get("live_game_checks") or {}).get("status", "not_run")
    may_advance = (verdict == "ready_for_human_review" and actual == "passed"
                   and pr.get("state") == "open")
    return {"pr": pr, "case": candidate, "report": report, "rounds": rounds,
            "latest": latest, "creative": creative, "verdict": verdict,
            "actual_status": actual, "may_advance": may_advance}


@app.middleware("http")
async def private_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "img-src 'self'; form-action 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; connect-src 'none'")
    return response


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _session(request):
        return RedirectResponse("/", status_code=303)
    return _login_form(request)


@app.post("/login")
def login(request: Request, token: str = Form(""), login_csrf: str = Form("")):
    # Do not depend on Origin/Referer: real browsers and reverse proxies
    # may rewrite or omit them. A 15-minute authenticated form challenge
    # is required before the token can be verified with GitHub.
    if not _login_challenge_ok(request, login_csrf):
        return _login_denied(request, "form_challenge_invalid",
            "Login form expired or was modified. Reload the page and try again.")
    token = token.strip()
    if len(token) < 20 or len(token) > 512:
        return _login_denied(request, "invalid_format",
            "Enter the full GitHub fine-grained personal access token.")
    try:
        user = _github(token, "/user")
    except GithubFailure as exc:
        return _login_denied(request, "github_identity_request",
            "GitHub could not verify the token: " + str(exc))
    if str(user.get("login", "")).casefold() != OWNER:
        return _login_denied(request, "wrong_github_account",
            "This token belongs to a different GitHub account. Use the hgunta account.")
    try:
        repo = _github(token, f"/repos/{REPO}")
    except GithubFailure as exc:
        return _login_denied(request, "private_repo_access",
            "GitHub couldn't access hgunta/dark-stories-factory with this token. "
            "Check that its resource owner is hgunta, that the private repository is selected, "
            "and that Contents has read access. Details: " + str(exc))
    if repo.get("private") is not True:
        return _login_denied(request, "repo_privacy_check",
            "GitHub could not confirm access to the private factory repository.")
    payload = {"token": token, "login": OWNER, "csrf": secrets.token_urlsafe(32)}
    encrypted = _cipher().encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, encrypted, max_age=COOKIE_TTL, httponly=True,
                        secure=True, samesite="lax", path="/")
    return response


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    user = _session(request)
    if not user or not hmac.compare_digest(user["csrf"], csrf):
        return _login_redirect()
    response = _login_redirect()
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/", response_class=HTMLResponse)
def queue_page(request: Request):
    user = _session(request)
    if user is None:
        return _login_redirect()
    try:
        current, historical = _pulls(user["token"])
    except GithubFailure as exc:
        return _failure(request, str(exc))
    return _html(request, "queue.html", current=current, historical=historical,
                 csrf=user["csrf"], reviewed=request.query_params.get("reviewed"))


@app.get("/cases/{number}", response_class=HTMLResponse)
def case_page(request: Request, number: int):
    user = _session(request)
    if user is None:
        return _login_redirect()
    if number < 1:
        return _failure(request, "Invalid case number.", status_code=404)
    try:
        detail = _case(user["token"], number)
    except GithubFailure as exc:
        return _failure(request, str(exc))
    return _html(request, "case.html", **detail, csrf=user["csrf"])


@app.post("/cases/{number}/review")
def decide(request: Request, number: int, csrf: str = Form(...),
           action: str = Form(...), note: str = Form("")):
    user = _session(request)
    if user is None:
        return _login_redirect()
    if not hmac.compare_digest(user["csrf"], csrf):
        return _failure(request, "Security check failed. Reload and try again.", status_code=403)
    if action not in REVIEW_ACTIONS:
        return _failure(request, "Unrecognized review decision.", status_code=400)
    if not note.strip() or len(note) > 1800:
        return _failure(request, "Provide a review note (1–1800 characters).", status_code=400)
    try:
        detail = _case(user["token"], number)
        if detail["pr"].get("state") != "open":
            raise GithubFailure("This case is already closed.")
        if action == "advance" and not detail["may_advance"]:
            raise GithubFailure("The case has not passed automated and actual-game checks. It cannot advance yet.")
        body = (
            "**Crack the Case private editorial decision: "
            + REVIEW_ACTIONS[action] + "**\n\n"
            + note.strip() + "\n\n"
            + "This decision does **not** publish or deploy the mystery. "
            + "Public release still requires human playtesting, an exact-hash "
              "approval, and a separately reviewed game PR."
        )
        _github(user["token"], f"/repos/{REPO}/issues/{number}/comments",
                method="POST", payload={"body": body})
        if action in ("advance", "reject"):
            _github(user["token"], f"/repos/{REPO}/pulls/{number}",
                    method="PATCH", payload={"state": "closed"})
    except GithubFailure as exc:
        return _failure(request, str(exc))
    return RedirectResponse("/?reviewed=" + action, status_code=303)
