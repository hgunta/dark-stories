import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';

// Check the production-sized, desktop-only CSS behavior before publishing.
// Browser viewport dimensions mimic the available CSS pixels after zoom.
const base = process.env.DESKTOP_URL || 'http://127.0.0.1:8765/';
const browser = await chromium.launch({ headless:true });
const page = await browser.newPage({viewport:{width:1280,height:850}});
const errors = [];
page.on('pageerror',e=>errors.push(e.message));

function check(cond, message, data) {
  if (!cond) throw Error(message + (data ? ': ' + JSON.stringify(data) : ''));
}
try {
  await page.goto(base + '?case=ms-002', {waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.querySelector('#game-view').hidden);
  check((await page.locator('#playing-title').textContent()).includes('Elevator'), 'Could not open test case');

  // Long conversation to ensure that the browser is actually scrolling it.
  await page.evaluate(() => {
    const chat = document.querySelector('#chat');
    for (let i=0;i<35;i++) {
      const item=document.createElement('div');
      item.className='msg ' + (i%2 ? 'bot':'user');
      item.textContent=(i%2 ? 'Yes. ':'Could he have used the elevator? ').repeat(3);
      chat.appendChild(item);
    }
  });
  for (const [width,height] of [[1280,850],[1000,710],[820,560],[720,490],[720,410]]) {
    await page.setViewportSize({width,height});
    await page.evaluate(() => { document.querySelector('#chat').scrollTop=1e6; });
    const box=await page.evaluate(()=>{
      const chat=document.querySelector('#chat');
      const premise=document.querySelector('#case-brief');
      const input=document.querySelector('#input');
      const shell=document.querySelector('.game-panel');
      const c=chat.getBoundingClientRect(),p=premise.getBoundingClientRect(),i=input.getBoundingClientRect();
      return {
        viewport:innerHeight,chatTop:c.top,chatBottom:c.bottom,
        premiseTop:p.top,premiseBottom:p.bottom,premisePosition:getComputedStyle(premise).position,
        inputTop:i.top,inputBottom:i.bottom,
        chatScrollable:chat.scrollHeight>chat.clientHeight+20,
        scrollTop:chat.scrollTop,bodyScrollHeight:document.body.scrollHeight,
        shellHeight:shell.getBoundingClientRect().height,
        desktopMatch:matchMedia('(min-width:651px)').matches
      };
    });
    check(box.desktopMatch,'Unexpected mobile breakpoint',{width,height,...box});
    check(box.chatScrollable && box.scrollTop>40,'Messages must scroll independently',{width,height,...box});
    check(box.premisePosition==='sticky','Premise must stick on desktop',{width,height,...box});
    check(Math.abs(box.premiseTop-box.chatTop)<35,'Premise must stay pinned when conversation scrolls',{width,height,...box});
    check(box.premiseBottom<box.chatBottom,'Premise must leave space for conversation',{width,height,...box});
    check(box.inputBottom <= height+3,'Composer must remain reachable after zoom',{width,height,...box});
  }

  // On small screens the approved mobile premise must continue scrolling away.
  await page.setViewportSize({width:390,height:750});
  await page.evaluate(()=>{document.querySelector('#chat').scrollTop=1e6});
  const mobile=await page.evaluate(()=>{
    const p=document.querySelector('#case-brief');
    return {position:getComputedStyle(p).position,scrollTop:document.querySelector('#chat').scrollTop};
  });
  check(mobile.position!=='sticky','Mobile premise should NOT be pinned',mobile);
  if(errors.length)throw Error('Browser errors: '+errors.join(' | '));
  console.log('DESKTOP CHAT SMOKE PASSED: pinned premise, responsive height and zoom-size fallback; mobile unchanged');
} catch(e) {
  console.error('DESKTOP CHAT SMOKE FAILED:',e.message);
  console.error('BROWSER ERRORS:',JSON.stringify(errors));
  process.exitCode=1;
} finally {await browser.close();}
