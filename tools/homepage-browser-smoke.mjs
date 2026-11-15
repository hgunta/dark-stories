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
  if (await page.locator('#browse-experiments').count() ||
      await page.locator('#experimental-section').count() ||
      await page.locator('#delete-playtest-token').count())
    throw Error('No separate experimental navigation or transcript deletion form should appear');
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
  await page.waitForFunction(() => document.querySelectorAll('#case-grid .case-tile').length === 5);
  const cards=await page.locator('#case-grid .case-tile').allTextContents();
  if (cards.length!==5 || cards.some(text=>/experimental|unreviewed/i.test(text)))
    throw Error('Expected five equally presented cases with no experimental labels: '+JSON.stringify(cards));
  if (!(await page.locator('#case-count').textContent()).includes('5 cases'))
    throw Error('Unified library count should include all five mysteries');
  if (!cards.some(text=>text.includes('CASE 004')) || !cards.some(text=>text.includes('CASE 005')))
    throw Error('Additional cases should use normal case numbers');
  const extraCard=page.locator('#case-grid .case-tile').filter({hasText:'CASE 004'});
  const extraTitle=(await extraCard.locator('.case-title').textContent()).trim();
  await extraCard.click();
  await page.waitForFunction(()=>!document.getElementById('game-view').hidden);
  if ((await page.locator('#playing-title').textContent()).trim()!==extraTitle ||
      (await page.locator('#playing-number').textContent()).trim()!=='CASE 004')
    throw Error('Additional case did not open in the normal game experience');
  if (await page.locator('#share-sheet-overlay').isVisible())
    throw Error('Consent cannot be assumed when opening an additional case');
  await page.locator('#back-to-cases').click();
  if (!(await page.locator('#library-section').isVisible()))
    throw Error('Returning from a case should show the unified library');
  // Mobile homepage should keep the featured action and a single browse link
  // without introducing horizontal scrolling or squeezed controls.
  await page.setViewportSize({width:390,height:760});
  const mobile=await page.evaluate(() => ({
    documentWidth:document.documentElement.scrollWidth,
    viewportWidth:innerWidth,
    featuredWidth:document.querySelector('.featured-case').getBoundingClientRect().width,
    browseButtons:document.querySelectorAll('#browse-cases').length
  }));
  if (mobile.documentWidth>mobile.viewportWidth+2 || mobile.featuredWidth>mobile.viewportWidth)
    throw Error('Homepage overflows mobile viewport: '+JSON.stringify(mobile));
  if (mobile.browseButtons!==1)
    throw Error('Mobile homepage must have one browse action');
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
  console.log(JSON.stringify({brand,first,firstNumber,second,secondNumber,gameName,singleBrowse:true,fiveUnifiedCases:true,noDeletionForm:true,defaultConsentOff:true,jsErrors}));
  console.log('HOMEPAGE MINIMAL UX SMOKE PASSED');
}catch(e){
  console.log('PAGE_ERRORS:',JSON.stringify(jsErrors));
  console.error('HOMEPAGE BROWSER SMOKE FAILED:',e.message);
  process.exitCode=1;
}finally{await browser.close();}
