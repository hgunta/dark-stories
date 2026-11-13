// Neon branch-scheduled retention purge, no public action or user payloads.
// The function proxy strips forged x-neon-* headers; only a Neon schedule
// invocation can reach the deletion code. No secrets or row contents logged.
const MAX_EXECUTION_MS = 10000;
const DELETIONS = [
  "DELETE FROM ds_playtest_transcript WHERE recorded_at < now() - interval '30 days'",
  "DELETE FROM ds_playtest_sessions WHERE created_at < now() - interval '90 days'",
];
function reply(data,status=200){return new Response(JSON.stringify(data),{
  status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}
});}
export default {
 async fetch(request) {
  if(request.method!=="POST")return reply({error:"Not found"},404);
  const header=request.headers.get("x-neon-trigger-invocation-id");
  if(!header)return reply({error:"Not authorized"},401);
  let body;
  try{body=await request.json();}catch{return reply({error:"Invalid invocation"},400);}
  if(!body || body.version!==1 || body.invocation_id!==header ||
     body.trigger?.type!=="schedule" ||
     body.trigger?.name!=="dark-stories-daily-purge" ||
     !Number.isFinite(Date.parse(body.data?.scheduled_at))){
    return reply({error:"Invalid invocation"},403);
  }
  const dsn=process.env.DATABASE_URL;
  if(!dsn)return reply({ok:false,error:"Database unavailable"},503);
  let endpoint;
  try{
    const u=new URL(dsn);
    if(u.protocol!=="postgres:"&&u.protocol!=="postgresql:")throw Error("invalid");
    const parts=u.hostname.split(".");
    if(parts.length<4)throw Error("invalid");
    parts[0]="api";
    endpoint="https://"+parts.join(".")+"/sql";
  }catch{return reply({ok:false,error:"Database unavailable"},503);}
  try{
    for(const query of DELETIONS){
      const response=await fetch(endpoint,{
        method:"POST",signal:AbortSignal.timeout(MAX_EXECUTION_MS),
        headers:{"Content-Type":"application/json",
                 "Neon-Connection-String":dsn,
                 "Neon-Raw-Text-Output":"true"},
        body:JSON.stringify({query,params:[]})
      });
      if(!response.ok)return reply({ok:false,error:"Database cleanup unsuccessful"},503);
    }
    return reply({ok:true,statements:DELETIONS.length});
  }catch{return reply({ok:false,error:"Database cleanup unavailable"},503);}
 }
};
