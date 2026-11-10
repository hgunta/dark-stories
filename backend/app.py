import os, uuid, sqlite3, time
from threading import RLock
from typing import Dict
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from feedback import FeedbackStore
from rate_limit import RequestLimiter
from multiplayer import append_public, public_snapshot
from dotenv import load_dotenv
from openai import OpenAI
from game import load_mystery, looks_like_hypothesis, check_solution, sanitize_output, classify_question, direct_yes_fact_question
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from analytics_recorder import AnalyticsRecorder
from typing import List
import json
import random, string


# load env vars
load_dotenv()
USE_API = os.getenv("USE_API", "false").lower() == "true"
API_KEY = os.getenv("OPENAI_API_KEY")

# set up OpenAI client only if using API
client = OpenAI(api_key=API_KEY) if USE_API and API_KEY else None
if USE_API and not API_KEY:
    raise RuntimeError("USE_API=true but no OPENAI_API_KEY set in backend/.env")

app = FastAPI(title="Dark Stories")
# No environment variable, startup hook, path, or endpoint can enable this.
analytics_recorder = AnalyticsRecorder()
# Local-only MVP: feedback is lost on restart; no disk or external collection.
feedback_store = FeedbackStore()
request_limiter = RequestLimiter()


def analytics_mode():
    return "ai" if os.getenv("USE_API", "false").lower() == "true" and client is not None else "offline"


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    route = getattr(request.scope.get("route"), "path", None)
    operation = {
        "/api/create_room": "create", "/api/message": "message",
        "/api/hint": "hint", "/api/reveal": "reveal", "/api/join/{room_code}": "join",
    }.get(route)
    if operation:
        analytics_recorder.error(operation, "invalid_request", analytics_mode(), http_status=422)
    return await request_validation_exception_handler(request, exc)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Serve the SPA index.html at '/'
@app.get("/", include_in_schema=False)
def root():
    return FileResponse(FRONTEND_DIR / "index.html")

# If you later add images/js/css files in frontend/, expose them under /static
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# 4-letter codes (avoid confusing chars like 0/O, 1/I)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # 24 chars, all caps, no I/O
def gen_code(existing: set[str]) -> str:
    for _ in range(100):  # try up to 100 times to avoid collision
        code = "".join(random.choice(ALPHABET) for _ in range(4))
        if code not in existing:
            return code
    raise RuntimeError("Could not generate a unique room code.")

# In-memory rooms and a code→room_id map
ROOMS: Dict[str, dict] = {}
CODE_MAP: Dict[str, str] = {}  # CODE -> room_id

# Process-local, monotonic idle expiry. This removes rooms/code mappings but
# does not retain historical identifiers or make rooms survive restarts.
ROOM_IDLE_SECONDS = 2 * 60 * 60
ROOM_LOCK = RLock()


def _expire_idle_rooms(now):
    """Caller holds ROOM_LOCK; cleanup is lazy on room requests."""
    expired = [
        rid for rid, room in ROOMS.items()
        if now - room.get("last_activity", now) >= ROOM_IDLE_SECONDS
    ]
    for rid in expired:
        room = ROOMS.pop(rid, None)
        if room is not None:
            code = room.get("code")
            if CODE_MAP.get(code) == rid:
                CODE_MAP.pop(code, None)
    return len(expired)


def find_room(room_id=None, room_code=None, *, touch=True):
    """Resolve and touch a live room atomically with expiry cleanup."""
    with ROOM_LOCK:
        now = time.monotonic()
        _expire_idle_rooms(now)
        room = ROOMS.get(room_id) if room_id else None
        if room is None and room_code:
            rid = CODE_MAP.get(room_code.strip().upper())
            room = ROOMS.get(rid) if rid else None
        if room is not None and touch:
            room["last_activity"] = now
        return room


class CreateRoomReq(BaseModel):
    mystery_id: str = "ms-001"

class RoomResp(BaseModel):
    room_id: str         # internal id (unchanged)
    room_code: str       # NEW: the 4-letter code
    premise: str
    title: str

class MsgReq(BaseModel):
    # Accept either room_id OR room_code (clients can use whichever they have)
    room_id: str | None = None
    room_code: str | None = None
    text: str

class JoinResp(BaseModel):
    room_id: str
    room_code: str
    title: str
    premise: str
    mystery_id: str
    solved: bool

class MsgResp(BaseModel):
    reply: str
    solved: bool

class PrivateGuessReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: str = Field(min_length=1, max_length=128)
    guess: str = Field(min_length=1, max_length=1000)


class PrivateGuessResp(BaseModel):
    correct: bool
    solved: bool
    reply: str


class FeedbackReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: str
    rating: int = Field(strict=True, ge=1, le=5)
    issue: Literal["none", "confusing_clues", "incorrect_answer", "spoiler", "other"] = "none"

@app.post("/api/create_room", response_model=RoomResp)
def create_room(req: CreateRoomReq):
    allowed, retry_after = request_limiter.allow_create()
    if not allowed:
        raise HTTPException(429, "Too many new games. Please try again shortly.",
                            headers={"Retry-After": str(retry_after)})
    try:
        m = load_mystery(req.mystery_id)
    except FileNotFoundError:
        analytics_recorder.error("create", "unknown_mystery", analytics_mode())
        raise HTTPException(404, "Mystery not found") from None
    except Exception:
        analytics_recorder.error("create", "internal", analytics_mode())
        raise HTTPException(503, "Could not start a game. Please try again.") from None
    with ROOM_LOCK:
        now = time.monotonic()
        _expire_idle_rooms(now)
        rid = uuid.uuid4().hex[:8]
        code = gen_code(set(CODE_MAP.keys()))
        ROOMS[rid] = {
            "id": rid,
            "mystery": m,
            "state": {
                "asked": 0,
                "hints_used": 0,
                "solved": False,
                "confirmed_true": set(),
                "confirmed_false": set(),
            },
            "forbidden": set(map(str.lower, m["forbidden_reveals"])),
            "code": code,
            "last_activity": now,
            "public_events": [],
            "next_public_seq": 1,
        }
        CODE_MAP[code] = rid
    analytics_recorder.start(ROOMS[rid], analytics_mode())
    return RoomResp(room_id=rid, room_code=code, premise=m["premise_public"], title=m["title"])

@app.get("/api/join/{room_code}", response_model=JoinResp)
def join(room_code: str):
    code = room_code.strip().upper()
    room = find_room(room_code=code)
    if room is None:
        analytics_recorder.error("join", "unknown_room", analytics_mode(), http_status=404)
        raise HTTPException(404, "Room not found")
    m, st = room["mystery"], room["state"]
    return JoinResp(
        room_id=room["id"],
        room_code=code,
        title=m["title"],
        premise=m["premise_public"],
        mystery_id=m["mystery_id"],
        solved=st["solved"]
    )

@app.get("/api/room_state/{room_code}")
def room_state(room_code: str):
    # Read-only polling does NOT renew the room inactivity deadline.
    room = find_room(room_code=room_code, touch=False)
    if room is None:
        raise HTTPException(404, "Room not found")
    with ROOM_LOCK:
        return public_snapshot(room)


def list_mysteries() -> List[dict]:
    mdir = (Path(__file__).resolve().parent / "mysteries")
    items = []
    for p in sorted(mdir.glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            items.append({"id": data["mystery_id"], "title": data["title"],
                          "difficulty": data.get("metadata", {}).get("difficulty", "medium"),
                          "tags": data.get("metadata", {}).get("tags", [])})
    return items

@app.get("/api/mysteries")

def api_mysteries():
    return list_mysteries()

def get_room_by_selector(room_id: str | None, room_code: str | None):
    return find_room(room_id=room_id, room_code=room_code)

@app.post("/api/feedback", status_code=201)
def submit_feedback(req: FeedbackReq):
    # Feedback requires a completed room; do not expose an admin/read API.
    room = find_room(room_id=req.room_id)
    if room is None:
        raise HTTPException(404, "Room not found")
    if not room["state"]["solved"]:
        raise HTTPException(409, "Finish the mystery before rating it")
    try:
        result = feedback_store.submit(req.room_id, room["mystery"]["mystery_id"], req.rating, req.issue)
    except (sqlite3.Error, OSError):
        raise HTTPException(503, "Feedback temporarily unavailable") from None
    if result == "duplicate":
        raise HTTPException(409, "Feedback already submitted for this game")
    if result == "full":
        raise HTTPException(503, "Feedback temporarily unavailable")
    return {"status": "received"}


@app.post("/api/hint", response_model=MsgResp)
def hint(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room:
        analytics_recorder.error("hint", "unknown_room", analytics_mode(), http_status=404)
        raise HTTPException(404, "Room not found")
    st = room["state"]; m = room["mystery"]
    hint_attempt = analytics_recorder.hint_requested(room, analytics_mode())
    i = st["hints_used"]
    if i < len(m["hints"]):
        st["hints_used"] += 1
        reply = f"Hint {st['hints_used']}: {m['hints'][i]}"
        analytics_recorder.hint_delivered(room, hint_attempt, st["hints_used"])
        with ROOM_LOCK:
            append_public(room, "hint", reply=reply)
    else:
        reply = "No more hints."
    return MsgResp(reply=reply, solved=st["solved"])

@app.post("/api/reveal", response_model=MsgResp)
def reveal(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room:
        analytics_recorder.error("reveal", "unknown_room", analytics_mode(), http_status=404)
        raise HTTPException(404, "Room not found")

    st = room["state"]
    m = room["mystery"]

    was_solved = st["solved"]
    # End the game (even if already solved, we still return the solution summary)
    st["solved"] = True
    analytics_recorder.revealed(room, analytics_mode(), was_solved)
    if not was_solved:
        with ROOM_LOCK:
            append_public(room, "revealed")
    return MsgResp(reply=f"🟥 Solution revealed: {m['solution_summary']}", solved=True)

@app.post("/api/private_guess", response_model=PrivateGuessResp)
def private_guess(req: PrivateGuessReq):
    """Only the requesting HTTP client receives feedback on the submitted guess.

    Ordinary /api/message traffic remains public; callers must explicitly use
    this endpoint for private guesses. No guess text is put in the room feed.
    """
    room = find_room(room_id=req.room_id)
    if room is None:
        raise HTTPException(404, "Room not found")
    with ROOM_LOCK:
        if room["state"]["solved"]:
            raise HTTPException(409, "This mystery has already ended")

    guess = req.guess.strip()
    if not guess:
        raise HTTPException(422, "Enter a solution guess")

    allowed, retry_after = request_limiter.allow_question(room["id"])
    if not allowed:
        raise HTTPException(429, "Too many questions. Please try again shortly.",
                            headers={"Retry-After": str(retry_after)})

    m = room["mystery"]
    # Classification is separate from public questioning: do not map any
    # guessed fact indices or write the guess into the shared question feed.
    prompt = (
        "You evaluate a private lateral-thinking mystery solution. "
        "Return ONLY moderator_decide with label Solved if the player's guess "
        "semantically matches the acceptable solution; otherwise label No. "
        "Do not reveal facts, the correct explanation, hints or nudges. "
        "Return empty fact_indices and short_explanation. "
        "Private acceptable solutions: " + json.dumps(m["acceptable_solutions"])
    )
    try:
        if analytics_mode() == "offline":
            # Deterministic local-preview fallback, not a semantic AI judge.
            correct = check_solution(guess, m["acceptable_solutions"])
        else:
            label, _, _ = classify_question(guess, prompt, client)
            correct = label == "Solved"
    except Exception:
        raise HTTPException(503, "Could not check your guess. Please retry.") from None

    with ROOM_LOCK:
        # A concurrent question, guess or reveal may have ended the game while
        # the moderator was processing. Never emit duplicate solve activity.
        if room["state"]["solved"] or ROOMS.get(room["id"]) is not room:
            raise HTTPException(409, "This mystery has already ended")
        if correct:
            room["state"]["solved"] = True
            append_public(room, "solved")

    return PrivateGuessResp(
        correct=correct, solved=correct,
        reply=("Correct! You solved the mystery." if correct
               else "Not quite. Keep investigating.")
    )


@app.post("/api/message", response_model=MsgResp)
def message(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room:
        analytics_recorder.error("message", "unknown_room", analytics_mode(), http_status=404)
        raise HTTPException(404, "Room not found")
    m = room["mystery"]; st = room["state"]; forbidden = room["forbidden"]

    # facts are now objects: {"text": str, "required": bool, (optional) truth: bool}
    def fact_text(f):
        if isinstance(f, str):
            return f  # backwards compatibility if any old files remain
        return f.get("text", "")

    def is_required(f):
        if isinstance(f, str):
            return True
        return f.get("required", True)

    indexed_facts_lines = []
    for i, f in enumerate(m.get("facts", [])):
        tag = "req" if is_required(f) else "opt"
        indexed_facts_lines.append(f"{i}. ({tag}) {fact_text(f)}")
    indexed_facts_str = "\n".join(indexed_facts_lines)


    if st["solved"]:
        return MsgResp(reply="Game over. Create a new room.", solved=True)

    text = req.text.strip()
    if text.lower() in ("/premise","/rules","/help"):
        if text.lower()=="/premise":
            return MsgResp(reply=f"Premise: {m['premise_public']}", solved=False)
        return MsgResp(reply="Ask yes/no questions. I answer Yes/No/Irrelevant/Unknown. Use /hint. Propose a solution when ready.", solved=False)

    # if looks_like_hypothesis(text):
    #     solved = check_solution(text, m["acceptable_solutions"])
    #     if solved:
    #         st["solved"] = True
    #         return MsgResp(reply=f"Solved! {m['solution_summary']}", solved=True)
    #     return MsgResp(reply="No.", solved=False)

    # Question → LLM or stub
    system_prompt = f"""
    You are the Dark Stories Moderator. You privately know the solution and all private facts.

    Your job: respond to the player's input with a strict label and a tiny optional nudge.
    Never reveal forbidden nouns or any direct spoilers.

    Allowed labels (exactly one):
    - "Yes"
    - "No"
    - "Ask a Yes/No question"
    - "Irrelevant"
    - "Unknown"
    - "Solved"

    General rules:
    - The player should ask yes/no questions. 
    - If the question is a closed-ended, interrogative sentence designed to elicit a simple "yes" or "no" response, confirming or denying a statement - Answer with a "Yes" or "No".\n    - IMPORTANT: Judge the *meaning*, not exact words. "Two fish", "2 fish", and "two goldfish" all describe two fish. If a player identifies a broader category that is logically true, answer Yes even if a more specific term exists.\n    - Do not say No because a true guess is incomplete. Identify a correct fact with Yes; the player needs a separate full causal explanation to solve the case.\n    - Never contradict an already established true fact or the private facts. Interpret pronouns ("they", "the couple") in context.\n    - Treat a question such as "Are they goldfish?" as a fact-check, NOT a solved full explanation.
    - If the question asked by player seeks more than just a "Yes" or "No", label "Ask a Yes/No question" and give a short nudge to rephrase.
    - If the question is about something unrelated to the mystery, label "Irrelevant".
    - If the question is related but cannot be determined from the facts, label "Unknown".
    - Do not output any other words as the primary label (no extra categories, no headings).

    Nudges:
    - For ordinary Yes/No questions, do not output nudges; only the Yes/No label.\n    - Optional for Unknown, Irrelevant or rephrasing requests. Max 10 words.
    - Must not contain forbidden nouns or direct spoilers.
    - Use nudges to guide the player toward productive yes/no questions.

    Hypotheses / solutions:
    - If the player proposes an explanation/solution, treat it as a hypothesis.
    - Label "Solved" only for a complete causal explanation matching an acceptable solution. An isolated correct fact ("it was fish") is not a complete solution.\n    - For fact-checking interrogatives, never label Solved: respond Yes or No.
    - If it does not match, label No (optionally add a short nudge).

    Fact mapping (critical for auto-solve):
    - Facts are listed below with indices.
    - When the player's input is a YES/NO QUESTION, return fact_indices: the indices of any facts the question directly tests.
    - Only include fact indices if the mapping is clear. Do not guess.
    - You may include multiple indices if one question tests multiple facts.
    - For "Ask a Yes/No question","Irrelevant", and "Unknown", leave fact_indices empty unless the question clearly tests a fact but cannot be answered yes/no (rare).

    Forbidden nouns (must never appear in your output):
    {m["forbidden_reveals"]}

    Public premise (you may restate this only):
    {m["premise_public"]}

    Private facts (indexed; do not reveal forbidden nouns):
    {indexed_facts_str}

    Acceptable solutions (private; do not reveal them verbatim):
    {m["acceptable_solutions"]}

    Output format:
    Use the tool moderator_decide with:
    - label: one of the allowed labels
    - short_explanation: optional <=10-word nudge
    - fact_indices: optional list of integers (see Fact mapping)
    """

    # system_prompt = f"""
    # You are the Dark Stories Moderator. You privately know the solution and facts.
    # Rules:
    # - Only reveal the public premise.
    # - Answer strictly with: Yes / No / AskYesNo / Irrelevant / Unknown.
    # - Optionally add <=10 words as a nudge (no spoilers).
    # - For hypotheses, say 'Solved' only if matching acceptable solutions; otherwise 'No'.
    # - Hints only on '/hint'. Never reveal forbidden nouns.
    # - If the question cannot be answered with Yes or No, respond "AskYesNo" and a short nudge.
    # Premise (public): {m["premise_public"]}
    # Facts (private): {m["facts"]}
    # Acceptable solutions (private): {m["acceptable_solutions"]}
    # Forbidden nouns (private): {m["forbidden_reveals"]}
    # """

    allowed, retry_after = request_limiter.allow_question(room["id"])
    if not allowed:
        raise HTTPException(429, "Too many questions. Please try again shortly.",
                            headers={"Retry-After": str(retry_after)})
    question_attempt = analytics_recorder.question(room, analytics_mode())
    origins = []
    direct = direct_yes_fact_question(text, m)
    try:
        if direct is not None:
            label, fact_indices = direct
            nudge = ""
            origins.append("authored_fact_alias")
        else:
            label, nudge, fact_indices = classify_question(text, system_prompt, client, observe_origin=origins.append)
    except Exception as exc:
        from openai import APITimeoutError
        code = ("invalid_ai_output" if isinstance(exc, json.JSONDecodeError) else
                "ai_timeout" if isinstance(exc, APITimeoutError) else
                "ai_failure" if analytics_mode() == "ai" else "internal")
        analytics_recorder.error("message", code, analytics_mode(), room=room, attempt=question_attempt)
        # Never return upstream exception text (which may include private inputs).
        # Leave the game open so the player can retry.
        raise HTTPException(503, "The moderator is unavailable. Please try again.") from None
    response_origin = origins[-1] if origins else ("offline_stub" if analytics_mode() == "offline" else "ai_fallback")

    ALLOWED = {"Yes", "No", "AskYesNo", "Irrelevant", "Unknown", "Solved"}

    # Record confirmations for fact-completion solve detection
    if label in {"Yes", "No"} and fact_indices:
        if label == "Yes":
            st["confirmed_true"].update(fact_indices)
        else:
            st["confirmed_false"].update(fact_indices)

    required_idxs = {
        i for i, f in enumerate(m.get("facts", []))
        if is_required(f)
    }

    # Since we omitted "truth" and author facts as true statements,
    # completion = all required facts confirmed via "Yes".
    if required_idxs and required_idxs.issubset(st["confirmed_true"]):
        st["solved"] = True
        analytics_recorder.answered(room, question_attempt, "solved", response_origin, "required_facts")
        with ROOM_LOCK:
            append_public(room, "solved")
        return MsgResp(reply=f"Solved! {m['solution_summary']}", solved=True)


    if label not in ALLOWED:
        label = "Unknown"
        nudge = "Please ask a yes/no question."

    # ✅ If the model declares it solved, actually end the game.
    if label == "Solved":
        st["solved"] = True
        analytics_recorder.answered(room, question_attempt, "solved", response_origin, "moderator_label")
        with ROOM_LOCK:
            append_public(room, "solved")
        return MsgResp(reply=f"Solved! {m['solution_summary']}", solved=True)

    if label == "AskYesNo":
        analytics_recorder.answered(room, question_attempt, "ask_yes_no", response_origin)
        base = "Cannot answer. Please ask a yes/no question."
        if nudge:
            base += f" {nudge}"
        with ROOM_LOCK:
            append_public(room, "question", question=text, reply="Ask a Yes/No question")
        return MsgResp(reply=base, solved=False)

    analytics_recorder.answered(room, question_attempt, label.lower(), response_origin)
    label = sanitize_output(label, forbidden)
    if nudge:
        nudge = sanitize_output(nudge, forbidden)

    st["asked"] += 1
    with ROOM_LOCK:
        append_public(room, "question", question=text, reply=label)
    out = label if label in {"Yes", "No"} or not nudge or nudge in {"Yes","No","Irrelevant","Unknown","Solved"} else f"{label}. {nudge}"\n    if response_origin == "authored_fact_alias" and label == "Yes":\n        out = "Yes. Good catch. Now work out what happened and submit your solution."
    return MsgResp(reply=out, solved=st["solved"])

