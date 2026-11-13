// Live acceptance test for the actual Render preview after PR #38.
// Creates fresh test rooms; does not change deployment configuration.
const base = 'https://dark-stories-preview.onrender.com';
async function api(path, body) {
  const res = await fetch(base + path, {
    ...(body ? {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {}),
    signal: AbortSignal.timeout(70000)
  });
  if (!res.ok) throw new Error(path + ': HTTP ' + res.status);
  return res.json();
}
const cases = [
  {
    name:'Exact reported screenshot answer',
    text:"did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
    expectedSolved:true
  },
  {
    name:'Normal factual question must not prematurely solve',
    text:"Are they fish?",
    expectedSolved:false
  },
  {
    name:'Full causal question with minor typo',
    text:"did the 2 goldfish die after the bow fell and broke and they suffocated?",
    expectedSolved:true
  },
];
let failed = false;
for (const scenario of cases) {
  const room = await api('/api/create_room',{mystery_id:'ms-001'});
  const response = await api('/api/message',{
    room_id:room.room_id,text:scenario.text
  });
  const correct = response.solved === scenario.expectedSolved;
  console.log(JSON.stringify({
    test:scenario.name,
    solved:response.solved,
    almost_solved:response.almost_solved ?? false,
    reply:response.reply,
    expectedSolved:scenario.expectedSolved,
    passed:correct
  }));
  if(!correct) failed = true;
}
if (failed) { console.error('LIVE AI SOLVE ACCEPTANCE FAILED'); process.exitCode = 1; }
else console.log('LIVE AI SOLVE ACCEPTANCE PASSED');
