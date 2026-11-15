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
  await page.clock.install();
  await page.goto(base+'?case=ms-002',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.getElementById('game-view').hidden);
  await page.locator('#playing-title').getByText('The Elevator Man').waitFor();
  if (!(await page.locator('#case-brief').isVisible())) throw Error('Premise must remain available');
  if (!(await page.locator('#chat > #case-brief').count()))
    throw Error('Premise must be a scrollable chat item, not fixed outside the chat');
  if (await page.locator('#case-brief summary').count()) throw Error('Premise must not have a toggle');
  if (await page.locator('#case-menu').count()) throw Error('Three-dot menu must be gone');
  if (await page.locator('#hint').evaluate(el => el.parentElement?.classList.contains('composer')) !== true)
    throw Error('Hint must be inside the composer, not in a new mobile controls row');
  if (await page.locator('#case-share').evaluate(el=>el.closest('.game-top-actions')===null))
    throw Error('Share action must be in header');
  if (await page.locator('#reveal').evaluate(el=>el.closest('.game-top-actions')===null))
    throw Error('Reveal action must be in header');
  if (!(await page.locator('#case-share').isVisible()) || !(await page.locator('#hint').isVisible()))
    throw Error('Share and Hint must be usable');
  if (!(await page.locator('#case-privacy').isVisible()))
    throw Error('Eligible playtest privacy control must remain accessible');
  await page.locator('#reveal').click();
  if (await page.locator('#case-finished').isVisible())
    throw Error('Canceling Reveal must not finish the game');
  if (!(await page.locator('#case-opening-question').textContent()).includes('Why does')) throw Error('Missing per-case call to action');
  if (await page.locator('#menu-solve').count() || await page.locator('#open-solution').count())
    throw Error('Redundant Solve case control is still shown');
  if (await page.locator('#game-goal').count()) throw Error('Goal paragraph must not distract under the premise');
  if (!(await page.locator('#input').getAttribute('placeholder')).includes('crack the case'))
    throw Error('Composer must explain what to do');
  await page.clock.fastForward(10100);
  await page.locator('#starter-nudge').waitFor();
  if (!(await page.locator('#starter-nudge').textContent()).includes('Try asking'))
    throw Error('Idle starter should offer an example question');
  await assertViewport('after ten-second idle starter');
  await assertViewport('before first question');
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('Should not interrupt before first question');
  await page.locator('#input').fill('Was the man short?');
  await page.locator('#send').click();
  await page.locator('.msg.bot').last().waitFor();
  await page.locator('#share-sheet-overlay:visible').waitFor();
  if (!(await page.locator('#chat > #case-brief').count()))
    throw Error('Premise should stay in conversation scrollback after a message');
  if (await page.locator('#starter-nudge').count()) throw Error('Starter nudge should disappear once player engages');
  if (consents!==0) throw Error('Prompt opened without consent');
  await page.locator('#share-sheet-no').click();
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('Not now did not dismiss sheet');
  if (consents!==0) throw Error('Not now must not send consent');
  await assertViewport('after prompt dismissal');
  await page.locator('#input').fill('Does he have an umbrella?');
  await page.locator('#send').click();
  await page.locator('.msg.bot').last().waitFor();
  if (await page.locator('#share-sheet-overlay').isVisible()) throw Error('One-time sheet repeated');
  await page.locator('#case-privacy').click();
  await page.locator('#share-sheet-overlay:visible').waitFor();
  await page.locator('#share-sheet-yes').click();
  await page.waitForFunction(()=>document.getElementById('share-sheet-overlay').hidden);
  if (consents!==1) throw Error('Explicit accept did not grant consent exactly once');
  if (!await page.evaluate(()=>Boolean(window.__receiptCopied))) throw Error('Deletion receipt not copied for future access');
  await page.setViewportSize({width:390,height:520});
  await assertViewport('short viewport');

  // Emulate the Android in-app-browser keyboard case: the layout viewport
  // stays tall, but the visual viewport becomes shorter and pans downward.
  // Without the offsetTop adjustment, the composer ends up too high/cropped.
  await page.locator('#input').focus();
  await page.evaluate(() => {
    const visual = window.visualViewport;
    if (!visual) throw Error('VisualViewport is required for keyboard regression');
    Object.defineProperty(visual, 'height', {configurable:true, value:285});
    Object.defineProperty(visual, 'offsetTop', {configurable:true, value:100});
    visual.dispatchEvent(new Event('resize'));
    visual.dispatchEvent(new Event('scroll'));
  });
  const keyboard = await page.evaluate(() => {
    const field=document.querySelector('#input').getBoundingClientRect();
    const shell=document.querySelector('body').getBoundingClientRect();
    const visual=window.visualViewport;
    const root=document.documentElement;
    const game=document.querySelector('#game-view').getBoundingClientRect();
    const panel=document.querySelector('.game-panel').getBoundingClientRect();
    const chat=document.querySelector('#chat').getBoundingClientRect();
    const brief=document.querySelector('#case-brief').getBoundingClientRect();
    const top=document.querySelector('.game-topline').getBoundingClientRect();
    const controls=document.querySelector('.controls').getBoundingClientRect();
    return {fieldTop:field.top,fieldBottom:field.bottom,shellTop:shell.top,
      shellHeight:shell.height,gameHeight:game.height,panelHeight:panel.height,
      chatHeight:chat.height,briefHeight:brief.height,topHeight:top.height,
      controlsHeight:controls.height,computedBodyHeight:getComputedStyle(document.body).height,
      visualHeightVar:root.style.getPropertyValue('--game-viewport-height'),
      visualOffsetVar:root.style.getPropertyValue('--game-viewport-offset-top'),
      visibleTop:visual.offsetTop,visibleBottom:visual.offsetTop+visual.height,
      height:visual.height,docScrollY:window.scrollY};
  });
  const conversation = await page.evaluate(() => ({
    chatViewport:document.querySelector('#chat').clientHeight,
    headerHidden:getComputedStyle(document.querySelector('.site-header')).display==='none',
    composing:document.body.classList.contains('game-composing'),
    scrollablePremise:document.querySelector('#case-brief').parentElement===document.querySelector('#chat'),
    chatScrollHeight:document.querySelector('#chat').scrollHeight
  }));
  if (!conversation.scrollablePremise || !conversation.composing || !conversation.headerHidden ||
      conversation.chatViewport<115) {
    throw Error('keyboard: too little chat space / premise not in scrollback '+JSON.stringify(conversation));
  }
  // Users can recover the entire premise by scrolling up; the game must not
  // remove or auto-collapse its text after the first message.
  await page.locator('#chat').evaluate(el=>{el.scrollTop=0;});
  if (!(await page.locator('#premise').textContent()).includes('10th floor'))
    throw Error('Premise missing from scrollback');
  if (Math.abs(keyboard.shellTop-keyboard.visibleTop)>3) {
    throw Error('keyboard: shell is not aligned to visible viewport '+JSON.stringify(keyboard));
  }
  if (keyboard.fieldBottom>keyboard.visibleBottom+3 ||
      keyboard.fieldBottom<keyboard.visibleBottom-48 ||
      keyboard.fieldTop<keyboard.visibleTop-3) {
    throw Error('keyboard: composer is not pinned immediately above keyboard '+JSON.stringify(keyboard));
  }

  await page.locator('#input').fill('This is the full explanation');
  await page.locator('#send').click();
  await page.locator('#case-finished:visible').waitFor();
  if (await page.locator('#input').isVisible()) throw Error('Solved game still shows composer');
  if (!(await page.locator('#case-result-share').isVisible()))
    throw Error('Solved result must remain shareable without a menu');
  if (await page.locator('#case-share').isVisible())
    throw Error('Do not show duplicate share actions when finished');
  if (errors.length) throw Error('JavaScript errors: '+errors.join(' | '));
  console.log('MOBILE CHAT SMOKE PASSED: direct Hint/Share/Reveal, privacy, keyboard composer, opt-in and completion');
} catch(error) {
  console.error('MOBILE CHAT SMOKE FAILED:',error.message);
  console.error('JS ERRORS',JSON.stringify(errors));
  process.exitCode=1;
} finally {await browser.close();}
