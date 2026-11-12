#!/usr/bin/env python3
"""Premise-first Dark Stories editorial experiment, NOT a game publisher.

Astra writes seven independent paradox seeds with hidden explanations. Sol
blind-screens premise only (never sees explanations) and a separate logical
editor audits explanations. Astra then develops only three chosen candidates.
The final Sol pass can reject all three. Dry-run by default.
"""
import argparse
import json
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from astra_story_batch import call_background, save

SEED_PROMPT = """You're an inventive writer of challenging lateral-thinking mysteries.
Generate EXACTLY SEVEN ORIGINAL TWO-SENTENCE public PREMISES, each with a
ONE-PARAGRAPH canonical explanation; make each mystery from a distinct family:
misinterpreted physical evidence, time/sequence, ordinary-object perspective,
unexpected human motive, location/scale, cause/effect reversal, and social role.

Our failing patterns: a technical noun solves everything; a contrived personal
tragedy is supplied as backstory; obvious first guess explains the whole puzzle;
a "twist" depends on lies in the premise; or an obscure specialist fact.
Do not use sensors, remote controls, recordings, fake deaths, twins, adoption,
child endangerment, domestic murder, celebrity, e-books, maintenance failures,
or generic spy conspiracies. No accidental tragedies added simply for darkness.
Aim for sharp, eerie or ironic detective logic with a genuinely earned reveal.

Treat each premise statement as a binding FACT, not rumor or mistaken
description unless clearly attributed as a character's claim.
The solution must explain every stated observation with an ordinary plausible
mechanism, a distinctive erroneous assumption and at least two additional
meaningful causal discoveries. No unverifiable coincidences to finish the story.
For every idea include one honest reason it might be weak.

Exactly this parseable plain-text format, no introductory prose:
=== IDEA 1 ===
TITLE: ...
PREMISE: ... (two sentences)
SOLUTION: ... (single paragraph)
ASSUMPTION: ...
FATAL_RISK: ...
=== IDEA 2 ===
... continue through IDEA 7.
"""
BLIND_PROMPT = """You are a skeptical first-time lateral-thinking game player.
You have never seen any solutions. For each supplied public premise:
- Propose three obvious guesses *from premise alone*, with no unseen facts.
- Flag if the central mechanism is obvious, or if there is no meaningful puzzle.
- Rate investigation potential 0-5 based only on premise.
Keep it concise. No invention of canonical plot facts.
"""
AUDIT_PROMPT = """You are a severe independent logic editor. Seven candidate public
premises and their proposed hidden solutions follow. For each:
- Check all public sentences for literal truth
- Identify any equally plausible cheaper explanation
- Check whether solution introduces gratuitous actors/assumptions
- Ask if the central twist could be guessed in one natural Yes/No question
- Decide: POTENTIAL or REJECT, with one-sentence reason.
A premise must be fair, coherent, surprising and independently investigable.
No enthusiasm padding; treat editorial gate as strict.\nAt the END give EXACTLY the line: PREFERRED_IDS: 1,3,6\nReplace numbers with the three most promising distinct candidate IDs.\nChoose based on genuine inevitability and mystery quality, not darkness.
"""
DEVELOP_PROMPT = """You are a demanding literary puzzle editor developing ONE
lateral-thinking mystery. You have its original premise/answer, a blind player's
first guesses, and a logic audit. Your challenge is to write a genuinely better
version without adding arbitrary facts or making the puzzle a long story.
You MAY replace the central mechanism and the premise if the audit exposes
an obvious or contrived twist. Never merely pad an obvious answer.

Deliver headings:
TITLE:
PUBLIC PREMISE (max 3 sentences, all literally true):
SOLUTION (max 160 words, causal):
CENTRAL MISTAKEN ASSUMPTION:
THREE MEANINGFUL REVELATIONS:
TRUE PLAYER QUESTIONS (at least 6):
FALSE PLAYER QUESTIONS (at least 3):
SPOILER-SAFE HINT 1:
SPOILER-SAFE HINT 2:
FAIRNESS / LITERAL TRUTH CHECK:
POTENTIAL SHORTCUT SOLUTION:
REMAINING FLAWS:
"""
CRITIQUE_PROMPT = """You are an adversarial editor of premium Dark Stories puzzles.
Score independently 0-5 on Surprise, Inevitability, Discoverability,
Literal Truth, and Emotional Payoff. Reject any weak premise where a trivial
guess solves everything or solution depends on made-up people / arbitrary acts.
State specific defects. Return:
SURPRISE: n
INEVITABILITY: n
DISCOVERABILITY: n
TRUTH: n
PAYOFF: n
VERDICT: SHORTLIST or REWORK or REJECT
WHY:
FIRST-QUESTION-COLLAPSE:
DOES_REVEAL_REINTERPRET_OR_ADD_BACKSTORY:
"""
def extract_ideas(text):
    chunks = re.split(r"(?m)^=== IDEA (\d+) ===\s*$",text)
    ideas=[]
    for idx in range(1,len(chunks),2):
        num=int(chunks[idx]); body=chunks[idx+1]
        def field(name):
            m=re.search(r"(?ms)^"+name+r":\s*(.*?)(?=^[A-Z_]+:\s*|\Z)",body)
            return m.group(1).strip() if m else ""
        item={"index":num,**{k.lower():field(k) for k in
              ["TITLE","PREMISE","SOLUTION","ASSUMPTION","FATAL_RISK"]}}
        if item["premise"] and item["solution"]:ideas.append(item)
    return ideas

def parse_scores(txt):
    vals=[]
    for key in ["SURPRISE","INEVITABILITY","DISCOVERABILITY","TRUTH","PAYOFF"]:
        m=re.search(r"(?m)^"+key+r":\s*([0-5])\b",txt)
        vals.append(int(m.group(1)) if m else 0)
    m=re.search(r"(?m)^VERDICT:\s*(SHORTLIST|REWORK|REJECT)",txt)
    return {"score":sum(vals),"verdict":m.group(1) if m else "REJECT"}

def execute(a):
    out={"stage":"started","seeds":[],"development":{},"critiques":{}}
    def persist():save(out,a.output)
    def invoke(model,prompt,max_tokens=7000,effort="low"):
        return call_background(model,prompt,max_tokens,effort,poll_seconds=5,cap_seconds=600)
    draft=invoke("gpt-6-astra",SEED_PROMPT,9000)
    out["seed_usage"]={k:draft.get(k) for k in ["status","input_tokens","output_tokens"]}
    out["seeds"]=extract_ideas(draft["text"])
    persist()
    print(f"SEEDS: {len(out['seeds'])}; status={draft['status']}",flush=True)
    if len(out["seeds"]) < 5: raise RuntimeError("Fewer than 5 usable premises; stop without further paid calls")
    premises="\n".join(f"{z['index']}. {z['title']}: {z['premise']}" for z in out["seeds"])
    blind=invoke("gpt-6.1-sol",BLIND_PROMPT+"\n"+premises,4000)
    audit=invoke("gpt-6.1-sol",AUDIT_PROMPT+"\n"+json.dumps(out["seeds"],ensure_ascii=False),4500)
    out["blind"]=blind;out["logic_audit"]=audit;persist()
    if not blind["text"] or not audit["text"]:
        raise RuntimeError("Independent evaluation incomplete; stop")
    # Development follows a separately recorded skeptical audit. If the
    # critic fails to choose three distinct valid IDs, fail closed rather
    # than spending on arbitrary candidates.
    m=re.search(r"(?m)^PREFERRED_IDS:\s*([0-9, ]+)",audit["text"])
    chosen_ids=[int(x) for x in re.findall(r"\d+",m.group(1))] if m else []
    seed_map={z["index"]:z for z in out["seeds"]}
    if len(chosen_ids)!=3 or len(set(chosen_ids))!=3 or any(
            i not in seed_map for i in chosen_ids):
        raise RuntimeError("Audit did not provide three valid distinct preferred IDs")
    chosen=[seed_map[i] for i in chosen_ids]
    out["chosen_indices"]=[z["index"] for z in chosen]
    persist()
    def develop(z):
        payload=(DEVELOP_PROMPT+"\nCANDIDATE:\n"+json.dumps(z,ensure_ascii=False)
                 +"\nBLIND NOTES:\n"+blind["text"]
                 +"\nLOGIC AUDIT:\n"+audit["text"])
        return z["index"],invoke("gpt-6-astra",payload,7500)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(develop,z) for z in chosen]):
            idx,res=f.result()
            out["development"][str(idx)]=res;persist()
            print(f"DEVELOP {idx}: {res['status']}; {len(res['text'])} chars",flush=True)
    def critique(idx,d):
        return idx,invoke("gpt-6.1-sol",CRITIQUE_PROMPT+"\n"+d["text"],3000)
    valid=[(i,d) for i,d in out["development"].items() if d["text"]]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(critique,i,d) for i,d in valid]):
            idx,res=f.result()
            out["critiques"][idx]=res;persist()
            print(f"CRITIQUE {idx}: {res['status']}",flush=True)
    out["ranked"]=sorted([{"index":i,**parse_scores(res["text"])}
                          for i,res in out["critiques"].items()],
                         key=lambda x:x["score"],reverse=True)
    out["stage"]="complete"
    persist()
    print("RANKED: "+json.dumps(out["ranked"]))
    if len(out["ranked"])<3:raise RuntimeError("Not enough developed concepts; no automatic retry")
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--execute",action="store_true")
    p.add_argument("--output",type=Path,default=Path(".story-evals/premise-first.json"))
    p.add_argument("--previous-estimated-spend",type=float,default=2.65)
    p.add_argument("--max-cumulative-usd",type=float,default=5)
    a=p.parse_args()
    # Conservative model-token reservation using exact API output caps,
    # and generous input limits; output tokens include hidden reasoning.
    # Astra: (9000 + 3*7500) output, 4*7000 input; Sol:
    # (4000 + 4500 + 3*3000) output, 5*12000 input.
    upper=((9000+3*7500)*50 + 4*7000*10 +
           (4000+4500+3*3000)*10 + 5*12000*2)/1_000_000
    print(f"Preflight conservative estimate ${upper:.2f} + prior ${a.previous_estimated_spend:.2f}.")
    if a.previous_estimated_spend+upper>a.max_cumulative_usd:
        p.error("Full design exceeds budget: reduce scope")
    if not a.execute:
        print("DRY RUN. No paid calls.")
        return 0
    if not os.getenv("OPENAI_API_KEY"):
        p.error("OPENAI_API_KEY missing")
    execute(a)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
