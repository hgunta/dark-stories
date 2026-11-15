import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';

const base=process.env.HOMEPAGE_URL || 'http://127.0.0.1:8765/';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
const jsErrors=[];
page.on('pageerror', err=>jsErrors.push(err.message));
page.on('dialog', dialog=>dialog.dismiss());
await page.addInitScript(() => {
  Object.defineProperty(navigator,'clipboard',{
    configurable:true,
    value:{writeText: async text=>{window.__copiedReceipt=text;}}
  });
});
await page.route('**/api/playtest/status', route => route.fulfill({
  status:200,contentType:'application/json',body:JSON.stringify({enabled:true,all_cases:true})
}));
await page.route('**/api/playtest/consent', route => route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({enabled:true,deletion_token:'example-only-disposable-test-receipt'})
}));
try {
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.locator('#start-game:not([disabled])').waitFor();
  const title=await page.title();
  if(!title.includes('Crack the Case'))throw Error('Incorrect browser title: '+title);
  // Landing should have one browse action, one start action, no extra pitch.
  if (await page.locator('#nav-cases').count()) throw Error('Duplicate header browse button still exists');
  if (await page.locator('#browse-cases').count() !== 1)
    throw Error('Expected exactly one Browse all cases action');
  if (await page.locator('#browse-experiments').isVisible())
    throw Error('Experimental cases should not compete on the initial homepage');
  const landingCopy=await page.locator('#landing-view .hero').textContent();
  if (/no daily login required|ask yes.or.no questions/i.test(landingCopy))
    throw Error('Redundant landing copy is still present');
  const brand=(await page.locator('.brand-wordmark').textContent()).trim();
  if(brand!=='CRACK THE CASE')throw Error('Incorrect visible branding: '+brand);
  const count=await page.locator('#case-grid .case-tile').count();
  if(count<2) throw Error('Expected multiple cases for featured rotation');
  const first=(await page.locator('#featured-title').textContent()).trim();
  const firstNumber=(await page.locator('#featured-number').textContent()).trim();
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('#start-game:not([disabled])').waitFor();
  const second=(await page.locator('#featured-title').textContent()).trim();
  const secondNumber=(await page.locator('#featured-number').textContent()).trim();
  if(first===second)throw Error('Featured case repeated on immediate reload');
  const fileSvg=await page.locator('.pixel-folder').getAttribute('viewBox');
  if(fileSvg!=='0 0 96 72')throw Error('Expected new crisp pixel-art folder SVG');
  // Library stays accessible via the single secondary homepage link.
  await page.locator('#browse-cases').click();
  if (!(await page.locator('#library-section').isVisible()))
    throw Error('Browse cases must open the library');
  if (!(await page.locator('#browse-experiments').isVisible()))
    throw Error('Experimental cases should remain reachable from the library');
  await page.locator('#browse-experiments').click();
  if (!(await page.locator('#experimental-section').isVisible()))
    throw Error('Experimental cases section should open');
  await page.locator('#back-to-library').click();
  if (!(await page.locator('#library-section').isVisible()))
    throw Error('Back to cases should reopen the library');
  await page.locator('#start-game').click();
  await page.waitForFunction(()=>!document.getElementById('game-view').hidden);
  const gameName=(await page.locator('#playing-title').textContent()).trim();
  if(gameName!==second)throw Error('Featured card opened '+gameName+' instead of '+second);
  // Optional sharing is intentionally deferred until after the first answer.
  if (await page.locator('#share-sheet-overlay').isVisible())
    throw Error('Consent sheet should not interrupt the premise');
  if (await page.locator('#playtest-opt-in').isChecked())
    throw Error('Sharing must default off');
  await page.locator('#input').fill('Is the location important?');
  await page.locator('#send').click();
  await page.locator('#share-sheet-overlay:visible').waitFor();
  if (await page.locator('#playtest-opt-in').isChecked())
    throw Error('Opening the consent sheet cannot enable sharing');
  await page.locator('#share-sheet-no').click();
  if (await page.locator('#share-sheet-overlay').isVisible())
    throw Error('Decline should dismiss the consent sheet');
  if(jsErrors.length)throw Error('Browser JavaScript errors: '+jsErrors.join(' | '));
  console.log(JSON.stringify({brand,first,firstNumber,second,secondNumber,gameName,singleBrowse:true,experimentLinkInLibrary:true,defaultConsentOff:true,jsErrors}));
  console.log('HOMEPAGE MINIMAL UX SMOKE PASSED');
}catch(e){
  console.log('PAGE_ERRORS:',JSON.stringify(jsErrors));
  console.error('HOMEPAGE BROWSER SMOKE FAILED:',e.message);
  process.exitCode=1;
}finally{await browser.close();}
