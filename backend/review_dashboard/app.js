"use strict";
const $=(id)=>document.getElementById(id);
const text=(tag,value)=>{const e=document.createElement(tag);e.textContent=String(value ?? "—");return e;};
const LABELS=["Yes","No","Irrelevant","Unknown","AskYesNo","AlmostSolved","Solved"];
const REASONS=["correct","false_negative","false_positive","incorrect_yes_no","unfair_solution","spoiler","unclear_story","other"];
let activeId=null;
async function get(path){
 const r=await fetch(path,{credentials:"same-origin",cache:"no-store"});
 if(!r.ok)throw Error("Review service unavailable ("+r.status+").");
 return r.json();
}
function status(msg){$("status").textContent=msg;}
function metric(value,label){
 const card=text("article","");card.append(text("strong",value===null?"—":value),text("span",label));return card;
}
async function refresh(){
 $("refresh").disabled=true;
 $("metrics").replaceChildren();$("sessions").replaceChildren();$("conversation").replaceChildren();
 status("Loading…");
 try{
  const data=await get("/api/review/overview");const s=data.summary;
  const pct=s.solved_rate===null?"—":Math.round(s.solved_rate*100)+"%";
  $("metrics").append(metric(s.sessions,"All sessions"),metric(pct,"Solve rate"),metric(s.average_rating ?? "—","Average rating"),metric(s.shared_sessions,"Shared sessions"),metric(s.reviewed_turns,"Reviewed turns"));
  $("feedback-notes").replaceChildren();
  for(const item of data.feedback_notes || []){
    const entry=document.createElement("article");entry.className="turn";
    entry.append(text("strong",item.case_id+" • "+item.rating+"/5"),text("small",item.issue||"none"),text("p",item.note));
    $("feedback-notes").append(entry);
  }
  if(!(data.feedback_notes||[]).length)$("feedback-notes").append(text("p","No written feedback yet."));
  for(const item of data.sessions){
    const b=document.createElement("button");b.type="button";b.className="session";
    b.append(text("strong",item.case_id+" • "+(item.outcome||"In progress")),
      text("span",(item.rating ? item.rating+"/5 • " : "")+item.turn_count+" turns • "+item.reviewed_turns+" reviewed"),
      text("small",new Date(item.started_at).toLocaleString()));
    b.addEventListener("click",()=>loadSession(item.id));
    $("sessions").append(b);
  }
  if(!data.sessions.length)$("sessions").append(text("p","No opted-in conversations available."));
  status("Review data loaded. "+data.sessions.length+" consented sessions shown.");
  if(activeId && data.sessions.some(x=>x.id===activeId))await loadSession(activeId);
  else activeId=null;
 }catch(e){status(e.message);}
 finally{$("refresh").disabled=false;}
}
async function loadSession(id){
 activeId=id;$("conversation").replaceChildren();
 try{
  const s=await get("/api/review/session/"+encodeURIComponent(id));
  $("conversation-heading").textContent=s.case_id+" • Conversation";
  $("session-meta").textContent="Revision "+s.revision+" • "+(s.outcome||"In progress")+" • Rating "+(s.rating??"—");
  for(const turn of s.turns){
    const item=document.createElement("article");item.className="turn";
    item.append(text("small","#"+turn.ordinal+" • "+turn.kind+" • "+new Date(turn.recorded_at).toLocaleTimeString()));
    if(turn.player_text)item.append(text("p","PLAYER: "+turn.player_text));
    item.append(text("p","MODERATOR: "+turn.moderator_text));
    item.append(text("small","Model label: "+turn.moderator_label));
    if(turn.kind==="question"||turn.kind==="private_guess")item.append(annotationForm(s.session_id,turn));
    $("conversation").append(item);
  }
  if(!s.turns.length)$("conversation").append(text("p","No messages are currently shared."));
 }catch(e){$("conversation").append(text("p",e.message));}
}
function pick(values,current){
 const sel=document.createElement("select");
 for(const val of values){const o=document.createElement("option");o.value=val;o.textContent=val;sel.append(o);}
 if(current)sel.value=current;
 return sel;
}
function annotationForm(id,turn){
 const form=document.createElement("form");form.className="review-form";
 const lbl=text("label","Correct response");const result=pick(LABELS,turn.correct_label||turn.moderator_label);
 const issueLabel=text("label","Reason");const reason=pick(REASONS,turn.reason_code||"correct");
 const button=text("button",turn.correct_label?"Update review":"Save review");
 button.type="submit";
 const message=text("small",turn.correct_label?"Reviewed":"Not reviewed");
 lbl.append(result);issueLabel.append(reason);form.append(lbl,issueLabel,button,message);
 form.addEventListener("submit",async(e)=>{
   e.preventDefault();button.disabled=true;message.textContent="Saving…";
   try{
      const response=await fetch("/api/review/label",{
       method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-Review-Intent":"annotate"},
       body:JSON.stringify({session_id:id,ordinal:turn.ordinal,correct_label:result.value,reason_code:reason.value})
      });
      if(!response.ok)throw Error("Review could not be saved ("+response.status+").");
      message.textContent="Saved";button.textContent="Update review";
   }catch(e){message.textContent=e.message;}
   finally{button.disabled=false;}
 });
 return form;
}
$("refresh").addEventListener("click",refresh);
refresh();
