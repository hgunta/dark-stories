import { chromium } from '/tmp/ds-playwright/node_modules/playwright/index.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';

const base=process.env.FONT_PREVIEW_URL || 'http://127.0.0.1:8765/';
const choices=[
  {slug:'pixelify',family:'Pixelify Sans'},
  {slug:'jersey15',family:'Jersey 15'},
  {slug:'jersey10',family:'Jersey 10'},
  {slug:'vt323',family:'VT323'}
];
const browser=await chromium.launch({headless:true});
const outDir='artifacts/font-comparisons';
mkdirSync(outDir,{recursive:true});
const report=[];
let sameFeaturedText=null;
let errors=[];
const assert=(value,msg,info)=>{if(!value)throw Error(msg+(info?' '+JSON.stringify(info):''));};
try {
for(const choice of choices){
  for(const device of [{name:'desktop',width:1100,height:840},{name:'mobile',width:390,height:760}]){
    const page=await browser.newPage({viewport:{width:device.width,height:device.height},deviceScaleFactor:1});
    page.on('pageerror',e=>errors.push({font:choice.slug,device:device.name,message:e.message}));
    const url=new URL(base);
    url.searchParams.set('font',choice.slug);
    await page.goto(url.toString(),{waitUntil:'domcontentloaded'});
    await page.locator('#start-game:not([disabled])').waitFor({timeout:30000});
    await page.evaluate(async family=>{
      await document.fonts.load('20px "'+family+'"');
      await document.fonts.ready;
    },choice.family);
    const landing=await page.evaluate(family=>{
      const selectors=['.brand-wordmark','.hero h1','#featured-title','#featured-premise','#start-game','#browse-cases'];
      return {family,
        selected:document.documentElement.dataset.fontCompare,
        fonts:selectors.map(selector=>({selector,font:getComputedStyle(document.querySelector(selector)).fontFamily})),
        pageWidth:document.documentElement.scrollWidth,viewport:innerWidth,
        fontLoaded:document.fonts.check('20px "'+family+'"'),
        featuredText:document.querySelector('#featured-premise').textContent.trim()};
    },choice.family);
    assert(landing.selected===choice.slug,'wrong font query selection',landing);
    assert(landing.fonts.every(x=>x.font.includes(choice.family)),'landing has mixed fonts',landing);
    assert(landing.fontLoaded,'remote font is not loaded',landing);
    assert(landing.pageWidth<=landing.viewport+3,'landing overflows horizontally',landing);
    assert(landing.featuredText.length>15,'featured case should have its actual premise',landing);
    if(sameFeaturedText===null)sameFeaturedText=landing.featuredText;
    assert(landing.featuredText===sameFeaturedText,
      'All font previews must show exactly the same featured mystery',landing);
    const homePath=`${outDir}/${choice.slug}-${device.name}-home.jpg`;
    writeFileSync(homePath,await page.screenshot({type:'jpeg',quality:82,fullPage:true}));

    const caseUrl=new URL(base);
    caseUrl.searchParams.set('font',choice.slug);
    caseUrl.searchParams.set('case','ms-002');
    await page.goto(caseUrl.toString(),{waitUntil:'domcontentloaded'});
    await page.locator('#game-view:visible').waitFor({timeout:30000});
    await page.evaluate(async family=>{
      await document.fonts.load('20px "'+family+'"');
      await document.fonts.ready;
      // Same illustrative messages in every variant; actual live case is real.
      const chat=document.querySelector('#chat');
      for(const [who,words] of [
        ['user','Is the man short?'],
        ['bot','Yes.'],
        ['user','Does rain change what he can reach?'],
        ['bot','Yes.']
      ]){
        const el=document.createElement('div');
        el.className='msg '+who;
        el.textContent=words;
        chat.appendChild(el);
      }
    },choice.family);
    const game=await page.evaluate(family=>{
      const selectors=['#playing-title','#back-to-cases','#premise','.chat .msg.user','.chat .msg.bot','#input','#hint'];
      const fonts=selectors.map(selector=>({selector,font:getComputedStyle(document.querySelector(selector)).fontFamily}));
      const input=document.querySelector('#input');
      const rect=input.getBoundingClientRect();
      return {family,fonts,fontLoaded:document.fonts.check('20px "'+family+'"'),
        pageWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
        viewportHeight:innerHeight,inputBottom:rect.bottom,
        premise:document.querySelector('#premise').textContent.trim(),
        placeholder:input.placeholder};
    },choice.family);
    assert(game.fonts.every(x=>x.font.includes(choice.family)),'case page has mixed fonts',game);
    assert(game.fontLoaded,'chat font not loaded',game);
    assert(game.pageWidth<=game.viewportWidth+3,'chat overflows horizontally',game);
    assert(game.inputBottom<=game.viewportHeight+5,'composer clipped in available viewport',game);
    assert(game.premise.length>25,'real premise missing',game);
    assert(game.placeholder.includes('Ask yes/no questions to crack the case'),'prompt changed',game);
    const gamePath=`${outDir}/${choice.slug}-${device.name}-chat.jpg`;
    writeFileSync(gamePath,await page.screenshot({type:'jpeg',quality:82,fullPage:true}));
    report.push({font:choice.family,slug:choice.slug,device:device.name,homePath,gamePath,allFontFamiliesMatch:true});
    await page.close();
  }
}
assert(errors.length===0,'browser JavaScript errors',errors);
writeFileSync(`${outDir}/report.json`,JSON.stringify(report,null,2));
console.log('FOUR FONT COMPARISONS PASSED',JSON.stringify(report));
} catch (e){
 console.error('FOUR FONT COMPARISONS FAILED',e.message);
 console.error('BROWSER ERRORS',JSON.stringify(errors));
 process.exitCode=1;
} finally {await browser.close();}
