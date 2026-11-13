const origin='https://dark-stories-preview.onrender.com';
const headers={'Cache-Control':'no-cache','Pragma':'no-cache'};
const results=[];
async function get(url,options={}){
 const response=await fetch(url,{...options,headers:{...headers,...options.headers},signal:AbortSignal.timeout(80000)});
 const data=await response.text();return {status:response.status,body:data,etag:response.headers.get('etag')};
}
for(const suffix of ['/api/mysteries','/api/mysteries?verify=pr44']){
 const r=await get(origin+suffix);
 let cases;try{cases=JSON.parse(r.body)}catch{cases=[]}
 const found=Array.isArray(cases)?cases.find(x=>x.id==='ms-003'):null;
 const result={path:suffix,http:r.status,etag:r.etag,title:found?.title,allTitles:Array.isArray(cases)?cases.map(x=>x.title):[],updated:found?.title==='The Last Match'};
 results.push(result);console.log('LIVE_CATALOG '+JSON.stringify(result));
}
const room=await get(origin+'/api/create_room',{
 method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mystery_id:'ms-003'})
});
let active;try{active=JSON.parse(room.body)}catch{active={}};
const session={http:room.status,title:active.title,premise:active.premise,updated:active.title==='The Last Match'&&String(active.premise).includes('broken matchstick')};
console.log('LIVE_ROOM '+JSON.stringify(session));
const correct=results.every(x=>x.updated)&&session.updated;
console.log(correct?'LIVE_DESERT_CASE_RELEASE_PASSED':'LIVE_DESERT_CASE_RELEASE_STALE');
if(!correct)process.exitCode=1;
