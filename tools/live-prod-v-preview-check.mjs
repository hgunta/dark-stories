// Read-only live release comparison. Do not print player data or credentials.
const targets = {
  production: 'https://dark-stories-8frx.onrender.com',
  preview: 'https://dark-stories-preview.onrender.com'
};
for (const [name, origin] of Object.entries(targets)) {
  for (const path of ['/', '/api/mysteries']) {
    try {
      const res=await fetch(origin+path,{signal:AbortSignal.timeout(100000),headers:{'Cache-Control':'no-cache'}});
      const body=await res.text();
      const out={site:name,path,status:res.status,finalUrl:res.url,
        title:body.match(/<title>([^<]+)/i)?.[1] ?? null,
        newBrand:body.includes('CRACK THE CASE'),
        oldBrand:body.includes('DARK STORIES'),
        randomized:body.includes('crack-the-case-last-featured'),
        newFolder:body.includes('viewBox="0 0 96 72"'),
        size:body.length,
        cacheControl:res.headers.get('cache-control'),
        etag:res.headers.get('etag')};
      if(path.includes('mysteries')) {
        try {const cases=JSON.parse(body);out.isArray=Array.isArray(cases);
          out.case3=cases.find?.(c=>c.id==='ms-003')?.title??null;
          out.caseCount=cases.length;
        }catch {out.responseSnippet=body.slice(0,100)}
      }
      console.log('DEPLOY_CHECK '+JSON.stringify(out));
    }catch(err){console.log('DEPLOY_CHECK '+JSON.stringify({site:name,path,error:String(err)}))}
  }
}

// Production release must now serve the requested latest main experience.
const target='https://dark-stories-8frx.onrender.com';
const [home,catalog]=await Promise.all([
 fetch(target+'/?post_deploy=80c1d755',{headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(95000)}),
 fetch(target+'/api/mysteries?post_deploy=80c1d755',{headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(95000)})
]);
const [html,raw]=await Promise.all([home.text(),catalog.text()]);
const cases=JSON.parse(raw);
const updated=home.ok && catalog.ok && html.includes('CRACK THE CASE') && html.includes('crack-the-case-last-featured') && html.includes('viewBox="0 0 96 72"') && cases.some(c=>c.id==='ms-003' && c.title==='The Last Match');
console.log('PRODUCTION_POST_DEPLOY '+JSON.stringify({homepage:home.status,catalog:catalog.status,brand:html.includes('CRACK THE CASE'),randomized:html.includes('crack-the-case-last-featured'),newFolder:html.includes('viewBox="0 0 96 72"'),case3:cases.find(c=>c.id==='ms-003')?.title,caseCount:cases.length,passed:updated}));
if(!updated)process.exitCode=1;
