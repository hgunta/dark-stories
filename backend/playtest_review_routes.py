"""Owner-only playtest review router.

Disabled until DARK_STORIES_REVIEW_PASSWORD is configured (>=32 chars).
HTTP Basic over HTTPS, constant-time credentials, no caching, strict origin
for edits, no browser-visible API keys or cookies. Never mount on production.
"""
import json
import os
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field

from playtest_review import ReviewStore, REVIEW_LABELS, REASON_CODES

ASSETS=Path(__file__).resolve().parent/"review_dashboard"
security=HTTPBasic(auto_error=False)
router=APIRouter(include_in_schema=False, prefix="/review")
api=APIRouter(include_in_schema=False,prefix="/api/review")

def _auth(credentials: HTTPBasicCredentials | None=Depends(security)):
    username=os.getenv("DARK_STORIES_REVIEW_USER","")
    password=os.getenv("DARK_STORIES_REVIEW_PASSWORD","")
    if not username or len(password)<32:
        # Fail closed if dashboard isn't explicitly configured.
        raise HTTPException(404,"Reviewer portal not enabled")
    if not credentials or not (
        secrets.compare_digest(credentials.username.encode(),username.encode())
        and secrets.compare_digest(credentials.password.encode(),password.encode())
    ):
        raise HTTPException(401,"Review credentials required",
                            headers={"WWW-Authenticate":'Basic realm="Dark Stories Reviewer", charset="UTF-8"'})
    return True

def _store(request: Request):
    store=request.app.state.playtest_store_for_review
    if store is None:
        raise HTTPException(503,"Review database unavailable")
    return ReviewStore(store)

def _safe_response(response: Response):
    response.headers["Cache-Control"]="no-store, private"
    response.headers["Pragma"]="no-cache"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]=(
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    return response

def _db_error():
    raise HTTPException(503,"Reviewer data temporarily unavailable") from None

@router.get("/")
def review_page(auth=Depends(_auth)):
    return _safe_response(FileResponse(ASSETS/"index.html",media_type="text/html"))

@router.get("/app.js")
def review_js(auth=Depends(_auth)):
    return _safe_response(FileResponse(ASSETS/"app.js",media_type="text/javascript"))

@router.get("/style.css")
def review_css(auth=Depends(_auth)):
    return _safe_response(FileResponse(ASSETS/"style.css",media_type="text/css"))

@api.get("/overview")
def overview(request:Request, response:Response, auth=Depends(_auth)):
    _safe_response(response)
    try:
        store=_store(request)
        return {"summary":store.summary(),"sessions":store.sessions(),
                "feedback_notes":store.feedback_notes()}
    except HTTPException:
        raise
    except Exception:
        _db_error()

@api.get("/session/{session_id}")
def session(session_id:str, request:Request,response:Response, auth=Depends(_auth)):
    _safe_response(response)
    try:
        data=_store(request).transcript(session_id)
        if data is None: raise HTTPException(404,"Consented session not found")
        return data
    except ValueError:
        raise HTTPException(422,"Invalid session identifier") from None
    except HTTPException:
        raise
    except Exception:
        _db_error()

class ReviewLabel(BaseModel):
    model_config=ConfigDict(extra="forbid")
    session_id:str=Field(min_length=1,max_length=50)
    ordinal:int=Field(ge=1,le=200)
    correct_label:str
    reason_code:str

@api.post("/label")
def label(request:Request,response:Response,body:ReviewLabel,auth=Depends(_auth)):
    _safe_response(response)
    # Browser CSRF defense: Authorization alone is insufficient with cached
    # Basic credentials. Only explicit same-origin JSON requests may edit.
    expected=os.getenv("DARK_STORIES_REVIEW_ORIGIN",
                       "https://dark-stories-preview.onrender.com")
    origin=request.headers.get("origin")
    intent=request.headers.get("x-review-intent")
    if origin!=expected or intent!="annotate" or not request.headers.get(
        "content-type","").startswith("application/json"):
        raise HTTPException(403,"Same-origin reviewer action required")
    if body.correct_label not in REVIEW_LABELS or body.reason_code not in REASON_CODES:
        raise HTTPException(422,"Invalid reviewer annotation")
    try:
        found=_store(request).annotate(body.session_id,body.ordinal,
                                      body.correct_label,body.reason_code)
        if not found: raise HTTPException(404,"Session unavailable or consent revoked")
        return {"saved":True}
    except ValueError:
        raise HTTPException(422,"Invalid reviewer annotation") from None
    except HTTPException:
        raise
    except Exception:
        _db_error()

@api.get("/export.jsonl")
def export(request:Request,auth=Depends(_auth)):
    try:
        examples=_store(request).reviewed_examples()
    except HTTPException:
        raise
    except Exception:
        _db_error()
    content="".join(json.dumps(e,ensure_ascii=False)+"\n" for e in examples)
    output=Response(content=content,media_type="application/x-ndjson")
    _safe_response(output)
    output.headers["Content-Disposition"]='attachment; filename="dark-stories-reviewed.jsonl"'
    return output
