import os, uuid
from typing import Dict
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from game import load_mystery, looks_like_hypothesis, check_solution, sanitize_output, classify_question
from fastapi.responses import FileResponse
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

# in-memory rooms
ROOMS: Dict[str, dict] = {}

@app.post("/api/create_room", response_model=RoomResp)
def create_room(req: CreateRoomReq):
    m = load_mystery(req.mystery_id)
    rid = uuid.uuid4().hex[:8]
    code = gen_code(set(CODE_MAP.keys()))
    ROOMS[rid] = {
        "mystery": m,
        "state": {
            "asked": 0,
            "hints_used": 0,
            "solved": False,
            "confirmed_true": set(),
            "confirmed_false": set()
        },
        "forbidden": set(map(str.lower, m["forbidden_reveals"])),
        "code": code
    }
    CODE_MAP[code] = rid
    return RoomResp(room_id=rid, room_code=code, premise=m["premise_public"], title=m["title"])

@app.get("/api/join/{room_code}", response_model=JoinResp)
def join(room_code: str):
    code = room_code.strip().upper()
    rid = CODE_MAP.get(code)
    if not rid or rid not in ROOMS:
        raise HTTPException(404, "Room not found")
    room = ROOMS[rid]
    m, st = room["mystery"], room["state"]
    return JoinResp(
        room_id=rid,
        room_code=code,
        title=m["title"],
        premise=m["premise_public"],
        mystery_id=m["mystery_id"],
        solved=st["solved"]
    )

def list_mysteries() -> List[dict]:
    mdir = (Path(__file__).resolve().parent / "mysteries")
    items = []
    for p in sorted(mdir.glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            items.append({"id": data["mystery_id"], "title": data["title"]})
    return items

@app.get("/api/mysteries")

def api_mysteries():
    return list_mysteries()

def get_room_by_selector(room_id: str | None, room_code: str | None):
    if room_id:
        room = ROOMS.get(room_id)
        if room: return room
    if room_code:
        rid = CODE_MAP.get(room_code.strip().upper())
        if rid:
            room = ROOMS.get(rid)
            if room: return room
    return None

@app.post("/api/hint", response_model=MsgResp)
def hint(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room: raise HTTPException(404, "Room not found")
    st = room["state"]; m = room["mystery"]
    i = st["hints_used"]
    if i < len(m["hints"]):
        st["hints_used"] += 1
        reply = f"Hint {st['hints_used']}: {m['hints'][i]}"
    else:
        reply = "No more hints."
    return MsgResp(reply=reply, solved=st["solved"])

@app.post("/api/reveal", response_model=MsgResp)
def reveal(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room:
        raise HTTPException(404, "Room not found")

    st = room["state"]
    m = room["mystery"]

    # End the game (even if already solved, we still return the solution summary)
    st["solved"] = True
    return MsgResp(reply=f"🟥 Solution revealed: {m['solution_summary']}", solved=True)

@app.post("/api/message", response_model=MsgResp)
def message(req: MsgReq):
    room = get_room_by_selector(req.room_id, req.room_code)
    if not room: raise HTTPException(404, "Room not found")
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
    - If the question is a closed-ended, interrogative sentence designed to elicit a simple "yes" or "no" response, confirming or denying a statement - Answer with a "Yes" or "No".
    - If the question asked by player seeks more than just a "Yes" or "No", label "Ask a Yes/No question" and give a short nudge to rephrase.
    - If the question is about something unrelated to the mystery, label "Irrelevant".
    - If the question is related but cannot be determined from the facts, label "Unknown".
    - Do not output any other words as the primary label (no extra categories, no headings).

    Nudges:
    - Optional. Max 10 words.
    - Must not contain forbidden nouns or direct spoilers.
    - Use nudges to guide the player toward productive yes/no questions.

    Hypotheses / solutions:
    - If the player proposes an explanation/solution, treat it as a hypothesis.
    - Label "Solved" if the hypothesis matches one of the acceptable solutions (semantic match).
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

    label, nudge, fact_indices = classify_question(text, system_prompt, client)

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
        return MsgResp(reply=f"Solved! {m['solution_summary']}", solved=True)


    if label not in ALLOWED:
        label = "Unknown"
        nudge = "Please ask a yes/no question."

    # ✅ If the model declares it solved, actually end the game.
    if label == "Solved":
        st["solved"] = True
        return MsgResp(reply=f"Solved! {m['solution_summary']}", solved=True)

    if label == "AskYesNo":
        base = "Cannot answer. Please ask a yes/no question."
        if nudge:
            base += f" {nudge}"
        return MsgResp(reply=base, solved=False)

    label = sanitize_output(label, forbidden)
    if nudge:
        nudge = sanitize_output(nudge, forbidden)

    st["asked"] += 1
    out = label if not nudge or nudge in {"Yes","No","Irrelevant","Unknown","Solved"} else f"{label}. {nudge}"
    return MsgResp(reply=out, solved=st["solved"])

