"""Owner-only editorial dashboard with least-privilege GitHub App sign-in.

Tokens live only in encrypted, Secure, HttpOnly cookies. No PAT entry, private
GitHub App key, database session store, or private case data on Render disk.
"""
from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import quote, urlencode

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
OAUTH_COOKIE = "ctc_github_oauth"
OAUTH_TTL = 60 * 10
GITHUB_CALLBACK = "https://crack-the-case-review.onrender.com/auth/github/callback"
FACTORY_REPO_ID = "1450638951"  # Verified GitHub repository ID; limits user token.
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
    """Read only GitHub App sessions; legacy PAT cookies are rejected."""
    encrypted = request.cookies.get(COOKIE_NAME)
    if not encrypted:
        return None
    try:
        data = json.loads(_cipher().decrypt(encrypted.encode("ascii"),
                                           ttl=COOKIE_TTL).decode("utf-8"))
        if (not isinstance(data, dict) or data.get("auth") != "github-app"
                or data.get("login") != OWNER
                or not isinstance(data.get("token"), str)
                or not isinstance(data.get("refresh_token"), str)
                or not isinstance(data.get("csrf"), str)
                or type(data.get("expires_at")) not in (int, float)
                or type(data.get("refresh_expires_at")) not in (int, float)):
            return None
        return data
    except (InvalidToken, ValueError, TypeError, UnicodeError, RuntimeError):
        return None


def _oauth_configured():
    return bool(os.getenv("REVIEW_GITHUB_APP_CLIENT_ID") and
                os.getenv("REVIEW_GITHUB_APP_CLIENT_SECRET"))


def _oauth_request(payload):
    """Server-to-server exchange; never return GitHub token errors to the browser."""
    if not _oauth_configured():
        raise GithubFailure("GitHub sign-in is not configured.")
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.post(
                "https://github.com/login/oauth/access_token",
                data=payload,
                headers={"Accept": "application/json",
                         "User-Agent": "crack-the-case-review"})
        if response.status_code != 200:
            raise GithubFailure("GitHub sign-in failed. Please try again.")
        result = response.json()
        if not isinstance(result, dict) or result.get("error"):
            raise GithubFailure("GitHub sign-in failed. Please try again.")
        return result
    except (httpx.RequestError, ValueError) as exc:
        raise GithubFailure("GitHub sign-in is temporarily unavailable.") from exc


def _oauth_tokens(data):
    """Require expiring GitHub App user tokens and their rotating refresh tokens."""
    if (not isinstance(data, dict) or not isinstance(data.get("token_type"), str) or data["token_type"].lower() != "bearer"
            or not isinstance(data.get("access_token"), str)
            or not data["access_token"].startswith("ghu_")
            or not isinstance(data.get("refresh_token"), str)
            or not data["refresh_token"].startswith("ghr_")
            or type(data.get("expires_in")) is not int
            or type(data.get("refresh_token_expires_in")) is not int
            or not 60 < data["expires_in"] <= 86400
            or not 60 < data["refresh_token_expires_in"] <= 365 * 86400):
        raise GithubFailure("GitHub did not return a usable expiring App session.")
    now = int(time.time())
    return {"token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": now + data["expires_in"],
            "refresh_expires_at": now + data["refresh_token_expires_in"]}


def _verify_owner(token):
    user = _github(token, "/user")
    if str(user.get("login", "")).casefold() != OWNER:
        raise GithubFailure("Sign in with the hgunta GitHub account.")
    repo = _github(token, f"/repos/{REPO}")
    if repo.get("private") is not True or repo.get("full_name") != REPO:
        raise GithubFailure("This GitHub App cannot access the private factory repository.")


def _set_session_cookie(response, data):
    encrypted = _cipher().encrypt(json.dumps(data).encode("utf-8")).decode("ascii")
    response.set_cookie(COOKIE_NAME, encrypted, max_age=COOKIE_TTL,
                        httponly=True, secure=True, samesite="lax", path="/")


def _authorized_session(request: Request):
    """Refresh expiring tokens transparently, keeping rotation in an encrypted cookie."""
    user = _session(request)
    if not user:
        return None
    now = int(time.time())
    if user["refresh_expires_at"] <= now + 120:
        return None
    if user["expires_at"] <= now + 120:
        try:
            refreshed = _oauth_tokens(_oauth_request({
                "client_id": os.environ["REVIEW_GITHUB_APP_CLIENT_ID"],
                "client_secret": os.environ["REVIEW_GITHUB_APP_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": user["refresh_token"],
            }))
            _verify_owner(refreshed["token"])
        except (GithubFailure, KeyError):
            return None
        user.update(refreshed)
        request.state.updated_session = user
    return user


def _login_form(request: Request, error=None):
    return _html(request, "login.html", error=error,
                 oauth_ready=_oauth_configured())


def _login_denied(request, reason, message):
    # Fixed reason codes only: no authorization code, token or request URL in logs.
    log.warning("review_login_denied reason=%s", reason)
    return _login_form(request, error=message)


def _clear_oauth(response):
    response.delete_cookie(OAUTH_COOKIE, path="/auth/github/callback")
    return response


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
            raise GithubFailure("GitHub authorization failed. Sign in with GitHub again.")
        if response.status_code == 404:
            raise GithubFailure("The private case or repository is unavailable with this GitHub App.")
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
    refreshed = getattr(request.state, "updated_session", None)
    if refreshed:
        _set_session_cookie(response, refreshed)
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


@app.get("/auth/github")
def github_start(request: Request):
    if not _oauth_configured():
        return _login_denied(request, "not_configured",
                             "GitHub sign-in is not configured yet.")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    payload = _cipher().encrypt(
        json.dumps({"state": state, "verifier": verifier}).encode("utf-8")
    ).decode("ascii")
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": os.environ["REVIEW_GITHUB_APP_CLIENT_ID"],
        "redirect_uri": GITHUB_CALLBACK,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "offline_access",
    })
    response = RedirectResponse(url, status_code=303)
    # Lax allows the GitHub->dashboard top-level GET callback. HttpOnly
    # prevents scripts from reading either OAuth state or PKCE verifier.
    response.set_cookie(OAUTH_COOKIE, payload, max_age=OAUTH_TTL,
                        secure=True, httponly=True, samesite="lax",
                        path="/auth/github/callback")
    return response


@app.get("/auth/github/callback")
def github_callback(request: Request, code: str = "", state: str = "",
                    error: str = ""):
    encrypted = request.cookies.get(OAUTH_COOKIE)
    try:
        if not encrypted or not 20 <= len(state) <= 160 or not 1 <= len(code) <= 512 or error:
            raise GithubFailure("GitHub sign-in was cancelled or expired. Please try again.")
        challenge = json.loads(_cipher().decrypt(encrypted.encode("ascii"),
                                                ttl=OAUTH_TTL).decode("utf-8"))
        if (not isinstance(challenge, dict)
                or not isinstance(challenge.get("state"), str)
                or not hmac.compare_digest(challenge["state"], state)
                or not isinstance(challenge.get("verifier"), str)):
            raise GithubFailure("GitHub sign-in expired or failed its security check.")
    except (GithubFailure, InvalidToken, ValueError, TypeError, UnicodeError):
        return _clear_oauth(_login_denied(request, "invalid_oauth_state",
            "GitHub sign-in expired or failed its security check. Please try again."))

    try:
        # Pin the user token to the private factory repository's verified ID.
        tokens = _oauth_tokens(_oauth_request({
            "client_id": os.environ["REVIEW_GITHUB_APP_CLIENT_ID"],
            "client_secret": os.environ["REVIEW_GITHUB_APP_CLIENT_SECRET"],
            "code": code,
            "code_verifier": challenge["verifier"],
            "redirect_uri": GITHUB_CALLBACK,
            "repository_id": FACTORY_REPO_ID,
        }))
        _verify_owner(tokens["token"])
    except (GithubFailure, KeyError) as exc:
        return _clear_oauth(_login_denied(request, "github_oauth_failed", str(exc)))

    session = {**tokens, "auth": "github-app", "login": OWNER,
               "csrf": secrets.token_urlsafe(32)}
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, session)
    return _clear_oauth(response)


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
    user = _authorized_session(request)
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
    user = _authorized_session(request)
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
    user = _authorized_session(request)
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
