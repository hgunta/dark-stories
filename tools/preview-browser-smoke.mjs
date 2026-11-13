import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';

const url = process.env.PREVIEW_URL || 'https://dark-stories-preview.onrender.com/';
const browser = await chromium.launch({headless: true});
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: '+e.message));
page.on('console', e => { if(e.type()==='error') errors.push('CONSOLE: '+e.text()); });
page.on('requestfailed', r => errors.push('REQUEST: '+r.url()+' '+r.failure()?.errorText));
try {
  const response = await page.goto(url,{waitUntil:'domcontentloaded',timeout:100000});
  console.log('URL:',page.url(),'HTTP:',response?.status());
  await page.waitForTimeout(1500);
  const state = await page.evaluate(() => ({
    title: document.title,
    ready:document.readyState,
    nav:!!document.getElementById('nav-cases'),
    scriptCount:document.scripts.length,
    startDisabled:document.getElementById('start-game')?.disabled,
    featured:document.getElementById('featured-title')?.textContent,
    loadingError:document.getElementById('landing-status')?.textContent,
    caseCount:document.getElementById('case-grid')?.children.length
  }));
  console.log('INITIAL:',JSON.stringify(state));
  console.log('ERRORS:',JSON.stringify(errors));
  await page.locator('#nav-cases').click({timeout:15000});
  await page.waitForTimeout(500);
  const unhidden = await page.locator('#library-section').evaluate(e => !e.hidden);
  console.log('AFTER_NAV: libraryVisible='+unhidden);
  if(!unhidden) throw Error('CLICK BROKEN: nav-cases failed to show library');
  await page.locator('#case-grid button').first().click({timeout:30000});
  await page.waitForTimeout(1500);
  const gameVisible=await page.locator('#game-view').evaluate(e=>!e.hidden);
  console.log('AFTER_CASE_CLICK: gameVisible='+gameVisible);
  console.log('FINAL_ERRORS:',JSON.stringify(errors));
  if(!gameVisible) throw Error('CLICK BROKEN: case tile failed to open game');
  console.log('PREVIEW INTERACTION SMOKE PASSED');
} catch(e) {
  console.log('FINAL_ERRORS:',JSON.stringify(errors));
  console.error('PREVIEW INTERACTION SMOKE FAILED:',e.message);
  process.exitCode=1;
} finally { await browser.close(); }
