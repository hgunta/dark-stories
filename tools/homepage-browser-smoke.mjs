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
  await page.locator('#start-game').click();
  await page.waitForFunction(()=>!document.getElementById('game-view').hidden);
  const gameName=(await page.locator('#playing-title').textContent()).trim();
  if(gameName!==second)throw Error('Featured card opened '+gameName+' instead of '+second);
  const optin=page.locator('#playtest-opt-in-panel');
  if(!(await optin.isVisible()))throw Error('Opt-in is not visible below chat');
  const below=await page.evaluate(()=>Boolean(
    document.getElementById('chat').compareDocumentPosition(document.getElementById('playtest-opt-in-panel'))
      & Node.DOCUMENT_POSITION_FOLLOWING
  ));
  if(!below)throw Error('Opt-in must appear after chat');
  if(await page.locator('#playtest-opt-in').isChecked())throw Error('Consent must default to off');
  await page.locator('#playtest-opt-in').check();
  await page.waitForFunction(()=>document.getElementById('playtest-opt-in-panel').hidden);
  const status=await page.locator('#playtest-share-status').textContent();
  if(!status.includes('Chat sharing enabled'))throw Error('Missing confirmation after consent');
  if(jsErrors.length)throw Error('Browser JavaScript errors: '+jsErrors.join(' | '));
  console.log(JSON.stringify({brand,first,firstNumber,second,secondNumber,gameName,optInVisibleBefore:true,optInHiddenAfter:true,jsErrors}));
  console.log('HOMEPAGE BROWSER SMOKE PASSED');
}catch(e){
  console.log('PAGE_ERRORS:',JSON.stringify(jsErrors));
  console.error('HOMEPAGE BROWSER SMOKE FAILED:',e.message);
  process.exitCode=1;
}finally{await browser.close();}
