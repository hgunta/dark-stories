// Short, read-only-in-configuration live AI correctness probe. Creates temporary game rooms.
const host = process.env.PREVIEW_URL || 'https://dark-stories-preview.onrender.com';
async function request(path, options = {}) {
  const res = await fetch(host + path, { signal: AbortSignal.timeout(65000), ...options });
  if(!res.ok) throw new Error(path + ' ' + res.status + ' ' + (await res.text()).slice(0,250));
  return res.json();
}
const schema = await request('/openapi.json');
console.log('LIVE API solution_attempt supported:', Boolean(schema.components.schemas.MsgReq.properties.solution_attempt));
const examples = [
  {name:'Screenshot exact wording',case:'ms-001',
    text:"did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?"},
  {name:'Unambiguous full explanation',case:'ms-001',
    text:"The couple were two goldfish. Their bowl fell and shattered, spilling the water, so they suffocated."},
  {name:'Explicit Solve case action',case:'ms-001',
    text:"did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
    solution_attempt:true},
];
for (const e of examples) {
  const room = await request('/api/create_room',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mystery_id:e.case})});
  try {
    const r=await request('/api/message',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({room_id:room.room_id,text:e.text,...(e.solution_attempt?{solution_attempt:true}:{})})});
    console.log(JSON.stringify({name:e.name,solved:r.solved,reply:r.reply,almost_solved:r.almost_solved??false}));
  }catch(err) {console.log(JSON.stringify({name:e.name,error:String(err)}));}
}
