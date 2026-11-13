import assert from "node:assert/strict";
import { test } from "node:test";
import purge from "../functions/playtestpurge/index.mjs";
const previous=process.env.DATABASE_URL;
const pretend="postgresql://user:PRIVATE_FAKE_PASSWORD@ep-fake.c-9.us-east-2.aws.neon.tech/neondb";
function delivery(token="synthetic"){
  return new Request("https://example.invalid/",{
    method:"POST",headers:{"content-type":"application/json",
    "x-neon-trigger-invocation-id":token},
    body:JSON.stringify({
      version:1,invocation_id:token,
      trigger:{type:"schedule",name:"dark-stories-daily-purge",id:"test"},
      data:{scheduled_at:"2026-11-13T00:00:00Z"}
    })
  });
}
test("unauthenticated requests never execute deletion",async()=>{
  let calls=0;const old=globalThis.fetch;globalThis.fetch=async()=>{calls++;throw Error("unexpected")};
  try{
    assert.equal((await purge.fetch(new Request("https://example.invalid/"))).status,404);
    const noHeader=new Request("https://example.invalid/",{method:"POST"});
    assert.equal((await purge.fetch(noHeader)).status,401);
    assert.equal(calls,0);
  }finally{globalThis.fetch=old}
});
test("trigger-matched delivery runs only both retention statements",async()=>{
  process.env.DATABASE_URL=pretend;
  const old=globalThis.fetch;
  const requests=[];
  globalThis.fetch=async(url,opts)=>{
    requests.push({url,opts});
    return new Response(JSON.stringify({rows:[]}),{status:200});
  };
  try{
    const result=await purge.fetch(delivery());
    assert.equal(result.status,200);
    assert.equal(requests.length,2);
    assert(requests.every(x=>x.url==="https://api.c-9.us-east-2.aws.neon.tech/sql"));
    assert(requests.every(x=>x.opts.headers["Neon-Connection-String"]===pretend));
    assert(requests[0].opts.body.includes("interval '30 days'"));
    assert(requests[1].opts.body.includes("interval '90 days'"));
  }finally{globalThis.fetch=old;process.env.DATABASE_URL=previous}
});
test("spoofed schedule payload fails before SQL",async()=>{
  process.env.DATABASE_URL=pretend;
  const old=globalThis.fetch;let count=0;
  globalThis.fetch=async()=>{count++;throw Error("unexpected")};
  try{
    const bad=delivery("different");
    const obj=await bad.json();
    obj.invocation_id="mismatch";
    const forged=new Request("https://example.invalid/",{
      method:"POST",headers:{"content-type":"application/json","x-neon-trigger-invocation-id":"different"},
      body:JSON.stringify(obj)
    });
    assert.equal((await purge.fetch(forged)).status,403);
    assert.equal(count,0);
  }finally{globalThis.fetch=old;process.env.DATABASE_URL=previous}
});
