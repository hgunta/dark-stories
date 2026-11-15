import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';

const base=process.env.STACK_URL || 'http://127.0.0.1:8765/';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1200,height:820}});
const errors=[];
const ratings=[];
const details=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('dialog',d=>d.accept());
await page.route('**/api/feedback',route=>{
  ratings.push(route.request().postDataJSON());
  return route.fulfill({status:201,contentType:'application/json',body:'{"status":"received"}'});
});
await page.route('**/api/feedback/details',route=>{
  details.push(route.request().postDataJSON());
  return route.fulfill({status:200,contentType:'application/json',body:'{"status":"received"}'});
});

function check(value,label,more) {
  if (!value) throw Error(label+(more?' '+JSON.stringify(more):''));
}
try {
  await page.goto(base,{waitUntil:'domcontentloaded'});
  check(!(await page.content()).includes('This shared mystery has ended. Start another game.'),
    'Ended shared mystery filler text must be removed from the app');
  await page.locator('#start-game:not([disabled])').waitFor();
  check(await page.locator('.pixel-magnifier-reference').count()===1,'approved magnifier is missing');
  const icon=await page.locator('.pixel-magnifier-reference').evaluate(el=>getComputedStyle(el).backgroundImage);
  check(icon.includes('data:image/png;base64,'),'magnifier must use actual pixel sprite');
  await page.locator('#browse-cases').click();
  await page.waitForFunction(()=>document.querySelectorAll('#case-grid .file-folder').length===5);
  check(await page.locator('#case-grid.case-file-stack').count()===1,'case library needs file-stack layout');
  const cards=page.locator('#case-grid .file-folder');
  check(await cards.count()===5,'need five file-folder tabs');
  for(let i=0;i<5;i++){
    const card=cards.nth(i);
    check((await card.locator('.case-number').textContent()).includes('00'+(i+1)),
      'folder tab incorrect',{index:i});
    check(await card.locator('.case-title').count()===1,'folder title missing');
  }
  const title=(await cards.nth(1).locator('.case-title').textContent()).trim();
  await cards.nth(1).click();
  await page.waitForFunction(()=>!document.querySelector('#game-view').hidden);
  check((await page.locator('#playing-title').textContent()).trim()===title,'folder did not start correct case');
  await page.locator('#reveal').click();
  await page.locator('#case-finished:visible').waitFor();
  const ratingUI=await page.evaluate(()=>({
    panel:document.querySelector('#feedback-panel').hidden,
    form:document.querySelector('#feedback-form').hidden,
    followup:document.querySelector('#feedback-followup').hidden,
    buttons:[...document.querySelectorAll('#feedback-panel button:not([hidden])')].filter(x=>!x.closest('[hidden]')).length,
    footer:document.querySelector('#finished-cases').textContent
  }));
  check(!ratingUI.panel && ratingUI.form && ratingUI.followup && ratingUI.buttons===5,
    'initial feedback must display only five stars',ratingUI);
  check(ratingUI.footer.includes('Play a different case'),'missing next case control');
  await page.locator('.rating-star[data-rating="4"]').hover();
  check(await page.locator('.rating-star.preview').count()===4,
    'hovering over star four must highlight stars one through four');
  await page.locator('.rating-star[data-rating="2"]').hover();
  check(await page.locator('.rating-star.preview').count()===2,
    'hovering over star two must highlight only first two');
  await page.mouse.move(10,10);
  check(await page.locator('.rating-star.preview').count()===0,
    'hovering away must clear unsaved preview');
  await page.locator('.rating-star[data-rating="3"]').focus();
  check(await page.locator('.rating-star.preview').count()===3,
    'keyboard focus should preview all stars through focused star');
  await page.locator('.rating-star[data-rating="4"]').click();
  check(await page.locator('.rating-star.preview').count()===0,
    'saved rating must clear temporary hover preview');
  await page.waitForFunction(()=>!document.querySelector('#feedback-form').hidden);
  check(ratings.length===1 && ratings[0].rating===4 && ratings[0].issue==='none' && !ratings[0].note,
    'rating must save on star tap',ratings);
  const selected=await page.locator('.rating-star.selected').count();
  check(selected===4,'four selected stars must be highlighted',{selected});
  await page.locator('#feedback-issue').selectOption('confusing_clues');
  await page.locator('#feedback-note').fill('A bit ambiguous.');
  await page.locator('#feedback-submit').click();
  await page.waitForFunction(()=>document.querySelector('#feedback-form').hidden);
  check(details.length===1 && details[0].rating===4 && details[0].issue==='confusing_clues'
       && details[0].note==='A bit ambiguous.', 'followup must save without rating again',details);
  check(ratings.length===1,'should not create another rating entry');
  const oldId=await page.evaluate(()=>window.CURRENT_MYSTERY||document.querySelector('#playing-title').textContent);
  await page.locator('#finished-cases').click();
  await page.waitForFunction(()=>!document.querySelector('#case-finished').hidden===false);
  check(await page.locator('#game-view').isVisible(),'next case should start without home detour');
  check(await page.locator('#feedback-panel').isHidden(),'next case must clear old stars');
  const newTitle=(await page.locator('#playing-title').textContent()).trim();
  check(newTitle!==title,'next case must differ from the finished mystery');
  await page.setViewportSize({width:390,height:760});
  await page.locator('#back-to-cases').click();
  const mobile=await page.evaluate(()=>({
    width:innerWidth,
    documentWidth:document.documentElement.scrollWidth,
    fileCount:document.querySelectorAll('#case-grid .file-folder').length,
    overflow:[...document.querySelectorAll('.file-folder')].some(el=>el.getBoundingClientRect().right>innerWidth+2)
  }));
  check(mobile.fileCount===5 && !mobile.overflow && mobile.documentWidth<=mobile.width+3,
    'folder stack must fit small mobile viewport',mobile);
  check(!errors.length,'browser JS errors',errors);
  console.log('FILE STACK + STAR FLOW PASSED: five pixel folders, exact sprite, instant rating, optional followup, direct next case, mobile fit');
}catch(error){
  console.error('FILE STACK + STAR FLOW FAILED:',error.message);
  console.error('BROWSER ERRORS:',JSON.stringify(errors));
  process.exitCode=1;
}finally{await browser.close();}
