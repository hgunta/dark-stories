import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';

const base=process.env.VISUAL_URL || 'http://127.0.0.1:8765/';
const browser=await chromium.launch({headless:true});
const errors=[];
const page=await browser.newPage({viewport:{width:1100,height:900},deviceScaleFactor:1});
page.on('pageerror', e=>errors.push(e.message));
const fail=(message, details) => { throw new Error(message+(details?' '+JSON.stringify(details):'')); };
const pixelFont=(font)=>font.includes('Press Start 2P');
const bodyFont=(font)=>font.includes('Inter');
async function capture(name){
  const bytes=await page.screenshot({type:'jpeg',quality:56,fullPage:true});
  mkdirSync('artifacts/approved-mock',{recursive:true});
  writeFileSync('artifacts/approved-mock/'+name+'.jpg',bytes);
  const b64=bytes.toString('base64');
  console.log('VISUAL_SHOT_START:'+name);
  for(let i=0;i<b64.length;i+=3000) console.log('VISUAL_SHOT_PART:'+name+':'+b64.slice(i,i+3000));
  console.log('VISUAL_SHOT_END:'+name);
}
try{
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.locator('#start-game:not([disabled])').waitFor();
  const landing=await page.evaluate(()=>{
    const css=(q)=>getComputedStyle(document.querySelector(q)).fontFamily;
    const r=document.querySelector('.featured-case').getBoundingClientRect();
    return {brand:css('.brand-wordmark'),headline:css('.hero h1'),featured:css('#featured-title'),
      premise:css('#featured-premise'),start:css('#start-game'),browse:css('#browse-cases'),
      bounds:{top:r.top,height:r.height,width:r.width},hasPremise:document.querySelector('#featured-premise').textContent.length>25,
      bodyScrollWidth:document.documentElement.scrollWidth};
  });
  for(const key of ['brand','headline','featured','premise','start','browse'])
    if(!pixelFont(landing[key]))fail('Mixed landing typography: '+key,landing);
  if(!landing.hasPremise)fail('Landing uses placeholder rather than true public case premise',landing);
  if(landing.bodyScrollWidth>1102)fail('Desktop landing horizontal scroll',landing);
  await capture('landing');
  await page.locator('#browse-cases').click();
  await page.waitForFunction(()=>document.querySelectorAll('#case-grid .file-folder').length===5);
  await page.evaluate(()=>{document.querySelector('#library-section').scrollIntoView({behavior:'instant',block:'start'});});
  const folders=await page.evaluate(()=>{
    const files=[...document.querySelectorAll('#case-grid .file-folder')];
    const boxes=files.map(x=>({y:x.getBoundingClientRect().top,h:x.getBoundingClientRect().height,
      font:getComputedStyle(x.querySelector('.case-title')).fontFamily,
      title:x.querySelector('.case-title').textContent}));
    return {boxes,step:boxes[1].y-boxes[0].y,caseCount:files.length,
      scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth};
  });
  if(folders.caseCount!==5||folders.step>=folders.boxes[0].h*.68||folders.step<38)
    fail('Folders must overlap tightly but retain an exposed title row',folders);
  if(folders.boxes.some(x=>!pixelFont(x.font)))fail('Folder titles must be pixel',folders);
  if(folders.scrollWidth>folders.viewport+2)fail('Folder library horizontal scroll',folders);
  await capture('folders');
  await page.locator('#case-grid .file-folder').nth(1).click();
  await page.waitForFunction(()=>!document.querySelector('#game-view').hidden);
  await page.evaluate(()=>{
    const chat=document.querySelector('#chat');
    for (const [text,who] of [
      ['Was someone else in the elevator?', 'user'],
      ['No.', 'bot'],
      ['Was he able to reach the button?', 'user'],
      ['No.', 'bot']
    ]) {
      const msg=document.createElement('div');
      msg.className='msg '+who;
      msg.textContent=text;
      chat.appendChild(msg);
    }
  });
  const game=await page.evaluate(()=>{
    const css=(q)=>getComputedStyle(document.querySelector(q)).fontFamily;
    const win=document.querySelector('#chat').getBoundingClientRect();
    return {title:css('#playing-title'),back:css('#back-to-cases'),reveal:css('#reveal'),
      composer:css('#input'),hint:css('#hint'),message:css('.chat .msg'),
      premise:css('#premise'),chatHeight:win.height,
      scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth};
  });
  for(const key of ['title','back','reveal','composer','hint'])
    if(!pixelFont(game[key]))fail('Mixed game chrome font: '+key,game);
  for(const key of ['message','premise'])
    if(!bodyFont(game[key]))fail('Conversation should stay readable Inter: '+key,game);
  if(game.chatHeight<180)fail('Game chat too small at desktop',game);
  await capture('game');
  await page.setViewportSize({width:390,height:760});
  await page.locator('#back-to-cases').click();
  await page.evaluate(()=>{document.querySelector('#library-section').scrollIntoView({behavior:'instant',block:'start'});});
  const mobile=await page.evaluate(()=>{
    const files=[...document.querySelectorAll('#case-grid .file-folder')];
    const a=files.map(x=>x.getBoundingClientRect());
    return {delta:a[1].top-a[0].top,height:a[0].height,
      width:document.documentElement.scrollWidth,viewport:innerWidth,
      browserFont:getComputedStyle(document.querySelector('#browse-cases')).fontFamily};
  });
  if(mobile.width>mobile.viewport+2||mobile.delta>=mobile.height*.7)
    fail('Mobile folder overlap or viewport broken',mobile);
  await capture('mobile-folders');
  if(errors.length)fail('Browser JS error',errors);
  console.log('APPROVED PIXEL MOCK VISUAL CONTRACT PASSED',JSON.stringify({landing,folders:{step:folders.step,height:folders.boxes[0].h},game,mobile}));
}catch(error){console.error('APPROVED PIXEL MOCK VISUAL CONTRACT FAILED',error.message);process.exitCode=1;}
finally{await browser.close();}
