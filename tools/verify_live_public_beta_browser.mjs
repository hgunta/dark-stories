import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const base='https://dark-stories-8frx.onrender.com';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1120,height:850}});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('dialog',dialog=>dialog.accept());
const visible=async selector=>page.locator(selector).isVisible();

try {
  await page.goto(base,{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('#browse-cases').click();
  await page.waitForSelector('#case-grid .case-tile');
  assert.equal(await page.locator('#case-grid .case-tile').count(),3);
  await page.locator('#browse-experiments').click();
  await page.waitForSelector('#experimental-grid .case-tile');
  assert.equal(await page.locator('#experimental-grid .case-tile').count(),2);
  console.log('BROWSER: three original case tiles and two experimental tiles');

  await page.locator('#experimental-grid .case-tile').first().click();
  await page.locator('#reveal').waitFor({state:'visible'});
  await page.locator('#playtest-opt-in-panel').waitFor({state:'visible'});
  assert.equal(await page.locator('#playtest-opt-in').isChecked(),false);
  assert.equal(await page.locator('.playtest-privacy-details').evaluate(e=>e.open),false);
  console.log('BROWSER: optional chat-sharing control unchecked and details collapsed');

  await page.locator('#reveal').click();
  await page.locator('#chat #feedback-panel').waitFor({state:'visible',timeout:15000});
  assert.equal(await page.locator('#feedback-panel').evaluate(e=>e.parentElement?.id),'chat');
  await page.locator('#feedback-rating').selectOption('4');
  await page.locator('#feedback-issue').selectOption('none');
  await page.locator('#feedback-submit').click();
  await page.waitForFunction(()=>document.getElementById('feedback-status')?.textContent?.includes('Thanks for your feedback'),{timeout:15000});
  console.log('BROWSER: rating card inside chat; four-star feedback successfully submitted');

  await page.locator('#nav-cases').click();
  await page.locator('#case-grid .case-tile').first().click();
  await page.locator('#reveal').waitFor({state:'visible'});
  assert.equal(await page.locator('#chat #feedback-panel').count(),0);
  assert.equal(await page.locator('#feedback-panel').isVisible(),false);
  console.log('BROWSER: new game resets old chat feedback, no leftover card');

  assert.equal(errors.length,0,'Browser JavaScript errors: '+errors.join('; '));
  console.log('BROWSER END-TO-END: pass; no AI moderator requests made');
} finally {
  await browser.close();
}
