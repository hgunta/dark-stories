import os, uuid, sqlite3, time
from threading import RLock
from typing import Dict
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from feedback import FeedbackStore
from playtest_store import PlaytestStore
from rate_limit import RequestLimiter
from multiplayer import append_public, public_snapshot
from dotenv import load_dotenv
from openai import OpenAI
from game import load_mystery, looks_like_hypothesis, check_solution, sanitize_output, classify_question, direct_yes_fact_question, looks_like_complete_theory_attempt, EXPERIMENTAL_IDS
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
# Preview-only, explicitly configured. Never infer storage from production flags.
_playtest_url = os.getenv("DARK_STORIES_PLAYTEST_DB_URL")
playtest_store = (PlaytestStore(_playtest_url) if
    os.getenv("DARK_STORIES_PLAYTEST_ENABLED") == "true" and _playtest_url else None)

def _playtest_record(room, kind, player_text, label):
    sid = room.get("playtest_session")
    if not sid or playtest_store is None:
        return
    with ROOM_LOCK:
        room["playtest_ordinal"] = room.get("playtest_ordinal",0)+1
        ordinal = room["playtest_ordinal"]
        opted = room.get("playtest_consented",False) and not room.get("playtest_multiplayer",False)
    try:
        playtest_store.record(sid,ordinal,kind,player_text,label,consent_on=opted)
    except Exception:
        # Collection may not change gameplay or leak user input into logs.
        pass

def _playtest_finish(room, outcome):
    sid = room.get("playtest_session")
    if sid and playtest_store is not None:
        try:
            playtest_store.finish(sid,outcome)
        except Exception:
            pass

def _playtest_hint(room):
    sid=room.get("playtest_session")
    if sid and playtest_store is not None:
        try:
            playtest_store.hint(sid)
        except Exception:
            pass



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

class QuestionMsgResp(MsgResp):
    # Add progress metadata only to /api/message; hints and reveals keep
    # their existing, strict two-field response contracts.
    almost_solved: bool | None = None

class PrivateGuessReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: str = Field(min_length=1, max_length=128)
    guess: str = Field(min_length=1, max_length=1000)


class PrivateGuessResp(BaseModel):
    correct: bool
    solved: bool
    reply: str


class PlaytestConsentReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: str = Field(min_length=1,max_length=128)

class PlaytestDeletionReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deletion_token: str = Field(min_length=20,max_length=150)

@app.get("/api/playtest/status", include_in_schema=False)
def playtest_status():
    return {"enabled": playtest_store is not None}

@app.post("/api/playtest/consent", include_in_schema=False)
def playtest_consent(req: PlaytestConsentReq):
    room = find_room(room_id=req.room_id)
    if not room or room["mystery"]["mystery_id"] not in EXPERIMENTAL_IDS:
        raise HTTPException(404,"Experimental session not found")
    if room.get("playtest_multiplayer") or room["state"]["solved"]:
        raise HTTPException(409,"Only active single-player sessions can opt in")
    sid=room.get("playtest_session")
    if not sid or playtest_store is None:
        raise HTTPException(503,"Transcript sharing is unavailable.")
    if room.get("playtest_consented"):
        raise HTTPException(409,"This session already opted in")
    try:
        token=playtest_store.consent(sid)
    except ValueError:
        raise HTTPException(409,"This session cannot enable transcript sharing") from None
    except Exception:
        raise HTTPException(503,"Transcript sharing is unavailable.") from None
    with ROOM_LOCK:
        room["playtest_consented"]=True
    return {"enabled":True,"deletion_token":token}

@app.post("/api/playtest/delete", include_in_schema=False)
def playtest_delete(req: PlaytestDeletionReq):
    if playtest_store is None:
        raise HTTPException(503,"Transcript deletion is temporarily unavailable")
    try:
        deleted=playtest_store.delete_receipt(req.deletion_token)
    except Exception:
        raise HTTPException(503,"Transcript deletion is temporarily unavailable") from None
    # Idempotent / non-enumerating: a reused token gets the same response.
    return {"deleted":True}

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
    # Structured metrics are recorded only for preview experimental cases.
    # A storage outage must never prevent opening a case. Feedback will
    # explicitly fail rather than pretending to be durable if no DB session.
    room=ROOMS[rid]
    if m["mystery_id"] in EXPERIMENTAL_IDS:
        room["playtest_session"]=None
        room["playtest_ordinal"]=0
        room["playtest_consented"]=False
        room["playtest_multiplayer"]=False
        if playtest_store is not None:
            try:
                room["playtest_session"]=playtest_store.start(
                    m["mystery_id"],os.getenv("RENDER_GIT_COMMIT","preview-unknown")[:40])
            except Exception:
                pass
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
    # A shared room can contain other people's questions. Stop collecting
    # transcript text and purge any earlier opt-in recording before join.
    if m["mystery_id"] in EXPERIMENTAL_IDS:
        sid=room.get("playtest_session")
        if sid and playtest_store is not None:
            try:
                playtest_store.disable_transcript(sid)
            except Exception:
                raise HTTPException(503,"Could not safely join this experimental room") from None
        with ROOM_LOCK:
            room["playtest_multiplayer"]=True
            room["playtest_consented"]=False
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

@app.get("/api/experimental_mysteries", include_in_schema=False)
def api_experimental_mysteries():
    # Only title/metadata: canonical solutions stay server-side in game rooms.
    cases = []
    for mid in sorted(EXPERIMENTAL_IDS):
        m = load_mystery(mid)
        cases.append({"id": mid, "title": m["title"],
                      "difficulty": m.get("metadata", {}).get("difficulty", "medium"),
                      "tags": ["experimental"]})
    return cases

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
    mid=room["mystery"]["mystery_id"]
    if mid in EXPERIMENTAL_IDS:
        sid=room.get("playtest_session")
        if not sid or playtest_store is None:
            raise HTTPException(503,"Durable experimental feedback is unavailable.")
        try:
            result=playtest_store.feedback(sid,req.rating,req.issue)
        except Exception:
            raise HTTPException(503,"Durable experimental feedback is unavailable.") from None
    else:
        try:
            result=feedback_store.submit(req.room_id,mid,req.rating,req.issue)
        except (sqlite3.Error,OSError):
            raise HTTPException(503,"Feedback temporarily unavailable") from None
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
        _playtest_hint(room)
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
        _playtest_finish(room,"revealed")
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
        "The core mechanism and its consequence are sufficient. "
        "Do NOT demand incidental details, wording, specific names, surnames, "
        "or guessed backstory. A paraphrase that explains the public paradox "
        "counts as Solved. Never grade on similarity of wording. "
        "Minimum sufficient explanation: " + m.get("minimum_solution", m["solution_summary"]) +
        " Private acceptable solutions: " + json.dumps(m["acceptable_solutions"])
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
    _playtest_record(room,"private_guess",guess,"solved" if correct else "no")
    if correct:
        _playtest_finish(room,"solved")

    return PrivateGuessResp(
        correct=correct, solved=correct,
        reply=("Correct! You solved the mystery." if correct
               else "Not quite. Keep investigating.")
    )


@app.post("/api/message", response_model=QuestionMsgResp, response_model_exclude_none=True)
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
    - "AlmostSolved"

    General rules:
    - The player should ask yes/no questions. 
    - If the question is a closed-ended, interrogative sentence designed to elicit a simple "yes" or "no" response, confirming or denying a statement - Answer with a "Yes" or "No".\n    - IMPORTANT: Judge the *meaning*, not exact words. "Two fish", "2 fish", and "two goldfish" all describe two fish. If a player identifies a broader category that is logically true, answer Yes even if a more specific term exists.\n    - Do not say No because a true guess is incomplete. Identify a correct fact with Yes; the player needs a separate full causal explanation to solve the case.\n    - Never contradict an already established true fact or the private facts. Interpret pronouns ("they", "the couple") in context.\n    - Confirm true partial facts with Yes; never reject a broader true category such as "two fish".
    - If a player names a central mechanism without explaining how it resolves the mystery, label AlmostSolved, not Solved.
    - Solved requires a coherent explanation linking the cause to the outcome, not merely the right object, device, actor, or setting.
    - The question mark does not by itself prevent solving, but question-form answers are confirmed through the separate Solve case step to prevent mistaken automatic endings.
    - Do not demand incidental details or precise authored wording.
    - If the question asked by player seeks more than just a "Yes" or "No", label "Ask a Yes/No question" and give a short nudge to rephrase.
    - If the question is about something unrelated to the mystery, label "Irrelevant".
    - If the question is related but cannot be determined from the facts, label "Unknown".
    - Do not output any other words as the primary label (no extra categories, no headings).

    Nudges:
    - Never output short_explanation for ANY label (empty string).
    - Never offer an unsolicited clue or mention a hidden mechanism, actor, device, location or solution direction.
    - Only explicitly requested /hint actions provide clues; those are handled separately outside this moderator.

    Hypotheses / solutions:
    - Solved: a genuinely complete causal account, preferably given as a proposed explanation.
    - AlmostSolved: the player correctly identifies the distinctive mechanism or most of the explanation, but has not explicitly connected cause and consequence.
    - Yes: a correct but isolated fact, not an explanation or a distinctive mechanism.
    - Never use AlmostSolved for speculative, incorrect, vague, or unrelated claims.
    - Use no unsolicited hints, even for AlmostSolved. The UI supplies a fixed spoiler-free invitation to explain.
    - If a true Yes/No question contains a full causal explanation, you may label Solved; the server will invite an explicit solution submission rather than auto-ending from the question.
    - An incorrect causal claim must not be treated as close merely because it mentions an important word.

    Fact mapping (critical for auto-solve):
    - Facts are listed below with indices.
    - When the player's input is a YES/NO QUESTION, return fact_indices: the indices of any facts the question directly tests.
    - Only include fact indices if the mapping is clear. Do not guess.
    - You may include multiple indices if one question tests multiple facts.
    - For "Ask a Yes/No question","Irrelevant", "AlmostSolved", and "Unknown", include only facts clearly tested, not inferred guesses.

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
    - label: one of the allowed labels (including AlmostSolved)
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

    # Players may explain the entire case in chat, not only through the
    # separate Solve case form. Check long causal theories independently
    # BEFORE the ordinary Yes/No moderator can downgrade them to AlmostSolved.
    # This criterion is semantic; the detector only chooses when to ask.
    if (m["mystery_id"] in EXPERIMENTAL_IDS and
            looks_like_complete_theory_attempt(text) and analytics_mode() == "ai"):
        solve_prompt = (
            "You are the Dark Stories final-theory judge. "
            "Return moderator_decide with label Solved ONLY when the theory "
            "explains the central mechanism AND why it resolves the observed "
            "contradiction; otherwise label No. "
            "Judge meaning, not wording. Do not demand incidental plot details, "
            "named objects, former surnames or precise authored phrases. "
            "Return empty short_explanation and fact_indices. "
            "Minimum sufficient explanation: " +
            m.get("minimum_solution", m["solution_summary"]) +
            " Other valid paraphrases: " + json.dumps(m["acceptable_solutions"])
        )
        try:
            solution_label, _, _ = classify_question(
                text, solve_prompt, client, observe_origin=origins.append)
            if solution_label == "Solved":
                with ROOM_LOCK:
                    if st["solved"] or ROOMS.get(room["id"]) is not room:
                        raise HTTPException(409, "This mystery has already ended")
                    st["solved"] = True
                    # Share only terminal status, never the player's theory.
                    append_public(room, "solved")
                _playtest_record(room,"question",text,"solved")
                _playtest_finish(room,"solved")
                analytics_recorder.answered(
                    room, question_attempt, "solved",
                    origins[-1] if origins else "ai_tool",
                    solve_method="moderator_label"
                )
                return QuestionMsgResp(
                    reply="✅ Correct! You solved the mystery.",
                    solved=True
                )
        except HTTPException:
            raise
        except Exception:
            # If the optional independent judge is unavailable, the normal
            # moderator route still works; no accidental win or spoiler.
            pass

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

    ALLOWED = {"Yes", "No", "AskYesNo", "Irrelevant", "Unknown", "AlmostSolved", "Solved"}

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

    # Facts are evidence, not proof of a causal explanation. A model can map
    # indices too eagerly, so completing them must NEVER auto-end a mystery.
    facts_complete = bool(required_idxs and required_idxs.issubset(st["confirmed_true"]))

    invalid_label = label not in ALLOWED
    if invalid_label:
        label = "Unknown"

    # Public moderation is exploratory. Even a model-issued Solved can be an
    # overconfident classification, so only explicit /api/private_guess may
    # actually close the case (or an intentional Reveal). This also gives the
    # player a clear chance to state the full explanation in their own words.
    if label == "Solved":
        label = "AlmostSolved"

    if label == "AlmostSolved" or (label == "Yes" and facts_complete):
        st["almost_solved"] = True
        _playtest_record(room,"question",text,"almost_solved")
        analytics_recorder.answered(room, question_attempt, "almost_solved", response_origin)
        # A near-solution may contain the twist; keep its text out of public
        # multiplayer feeds just as we do for the explicit private guess.
        return QuestionMsgResp(
            reply="Yes. You're close — explain how the pieces fit together.",
            solved=False, almost_solved=True
        )

    if label == "AskYesNo":
        _playtest_record(room,"question",text,"ask_yes_no")
        analytics_recorder.answered(room, question_attempt, "ask_yes_no", response_origin)
        base = "Cannot answer. Please ask a yes/no question."
        # Unsolicited nudges have caused spoilers; /hint is the only clue channel.
        with ROOM_LOCK:
            append_public(room, "question", question=text, reply="Ask a Yes/No question")
        return MsgResp(reply=base, solved=False)

    analytics_recorder.answered(room, question_attempt, label.lower(), response_origin)
    label = sanitize_output(label, forbidden)
    # Never surface model-generated nudges to players; even non-forbidden
    # wording can disclose the hidden solution by implication.
    nudge = ""

    st["asked"] += 1
    with ROOM_LOCK:
        append_public(room, "question", question=text, reply=label)
    out = ("Unknown. Please ask a yes/no question." if invalid_label else
           "Unknown. (offline mode)" if response_origin == "offline_stub" and label == "Unknown" else
           label)
    if response_origin == "authored_fact_alias" and label == "Yes":
        out = "Yes. Good catch. Now work out what happened and submit your solution."
    stored_label = label.lower() if label.lower() in {
        "yes","no","unknown","irrelevant","almost_solved","solved"
    } else "unknown"
    _playtest_record(room,"question",text,stored_label)
    return MsgResp(reply=out, solved=st["solved"])

