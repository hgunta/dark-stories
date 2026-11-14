import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';

const base=process.env.MOBILE_URL || 'http://127.0.0.1:8765/';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:390,height:760},isMobile:true,hasTouch:true,deviceScaleFactor:2});
const page=await context.newPage();
const errors=[];
let consents=0;
page.on('pageerror', err => errors.push(err.message));
page.on('dialog', dialog => dialog.dismiss());
await page.addInitScript(() => {
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
    writeText: async value => { window.__receiptCopied=value; }
  }});
});
await page.route('**/api/playtest/status', route=>route.fulfill({
  status:200,contentType:'application/json',body:JSON.stringify({enabled:true,all_cases:true})
}));
await page.route('**/api/playtest/consent', route=>{
  consents++;
  return route.fulfill({status:200,contentType:'application/json',
    body:JSON.stringify({enabled:true,deletion_token:'test-only-receipt'})});
});
await page.route('**/api/message', async route=>{
  const request=route.request().postDataJSON();
  return route.fulfill({status:200,contentType:'application/json',
    body:JSON.stringify({reply:request.text.includes('full explanation')?'✅ Correct! You solved the mystery.':'Yes.',
      solved:request.text.includes('full explanation'),almost_solved:false})});
});
async function assertViewport(label) {
  const info=await page.evaluate(()=>{
    const r=document.querySelector('#input').getBoundingClientRect();
    const end=document.querySelector('#case-finished');
    const composer=document.querySelector('.controls');
    const done=!end.hidden;
    return {inputBottom:r.bottom,composerBottom:composer.getBoundingClientRect().bottom,
      done,viewport:window.visualViewport?.height||innerHeight,
      outerOverflow:document.documentElement.scrollHeight-document.documentElement.clientHeight};
  });
  if (!info.done && info.inputBottom>info.viewport+3) throw Error(label+': input hidden under viewport '+JSON.stringify(info));
  if (info.outerOverflow>4) throw Error(label+': document scrolls, should only scroll chat '+JSON.stringify(info));
}
try {
  await page.goto(base+'?case=ms-002',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.getElementById('game-view').hidden);
  await page.locator('#playing-title').getByText('The Elevator Man').waitFor();
  if (!(await page.locator('#case-brief').evaluate(el=>el.open))) throw Error('Premise must start expanded');
  await assertViewport('before first question');
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('Should not interrupt before first question');
  await page.locator('#input').fill('Was the man short?');
  await page.locator('#send').click();
  await page.locator('.msg.bot').last().waitFor();
  await page.locator('#share-sheet-overlay:visible').waitFor();
  if (await page.locator('#case-brief').evaluate(el=>el.open)) throw Error('Premise did not collapse after question');
  if (consents!==0) throw Error('Prompt opened without consent');
  await page.locator('#share-sheet-no').click();
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('Not now did not dismiss sheet');
  if (consents!==0) throw Error('Not now must not send consent');
  await assertViewport('after prompt dismissal');
  await page.locator('#input').fill('Does he have an umbrella?');
  await page.locator('#send').click();
  await page.locator('.msg.bot').last().waitFor();
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('One-time sheet repeated');
  await page.locator('#case-menu > summary').click();
  await page.locator('#menu-privacy').click();
  await page.locator('#share-sheet-overlay:visible').waitFor();
  await page.locator('#share-sheet-yes').click();
  await page.waitForFunction(()=>document.getElementById('share-sheet-overlay').hidden);
  if (consents!==1) throw Error('Explicit accept did not grant consent exactly once');
  if (!await page.evaluate(()=>Boolean(window.__receiptCopied))) throw Error('Deletion receipt not copied for future access');
  await page.setViewportSize({width:390,height:520});
  await assertViewport('short viewport');
  await page.locator('#input').fill('This is the full explanation');
  await page.locator('#send').click();
  await page.locator('#case-finished:visible').waitFor();
  if (await page.locator('#input').isVisible()) throw Error('Solved game still shows composer');
  if (errors.length) throw Error('JavaScript errors: '+errors.join(' | '));
  console.log('MOBILE CHAT SMOKE PASSED: fixed composer, collapsible premise, opt-in consent, completion');
} catch(error) {
  console.error('MOBILE CHAT SMOKE FAILED:',error.message);
  console.error('JS ERRORS',JSON.stringify(errors));
  process.exitCode=1;
} finally {await browser.close();}
